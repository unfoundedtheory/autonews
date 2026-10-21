"""Owner-selected replacement suggestions for rejected Manual Post news.

Only original official-source candidates are presented. No AI calls are made
until the owner selects one. A draft, including rejected drafts, can never be
re-offered as a fresh story.
"""
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, case
from .models import Story, Draft, Audit
from .editorial import trusted_source
from .research import sort_candidates
from .telegram_ui import clean_text
from .telegram import with_home_button

MAX_CHOICES = 4
SKIP_TERMS = ('nfl', 'football', 'stadium', 'tailgate', 'flyover', 'sports fans')


def available_replacements(db, rejected_draft, actor, limit=MAX_CHOICES):
    """Recommend distinct un-drafted stories that were not offered before."""
    if rejected_draft.status != 'rejected':
        return []
    already_drafted = select(Draft.story_id)
    recent_failures = set(db.execute(select(Audit.draft_id).where(
        Audit.event == 'candidate_prepare_failed',
        Audit.created_at >= datetime.now(timezone.utc)-timedelta(hours=3),
    )).scalars().all())
    old_offers = db.execute(select(Audit).where(
        Audit.event == 'replacement_offered',
        Audit.actor == str(actor),
    ).order_by(Audit.id.desc()).limit(300)).scalars().all()
    previously_shown = {
        audit.draft_id for audit in old_offers
        if (audit.detail or {}).get('rejected_draft_id') == rejected_draft.id
    }
    queue = db.execute(select(Story).where(
        Story.verification_status == 'needs_fact_check',
        Story.id.not_in(already_drafted),
    ).order_by(
        case((Story.topic.in_(['astronomy', 'space']), 0), else_=1),
        Story.published_at.desc(), Story.created_at.desc()
    ).limit(250)).scalars().all()
    items = []
    for story in sort_candidates(queue):
        if (story.id == rejected_draft.story_id or story.id in previously_shown
                or story.id in recent_failures
                or not trusted_source(story.source_url)
                or any(term in story.title.casefold() for term in SKIP_TERMS)):
            continue
        items.append(story)
        if len(items) == limit:
            break
    return items


def replacement_keyboard(draft, stories):
    rows=[]
    for index, story in enumerate(stories, 1):
        rows.append([
            {'text':f'📰 Buat Berita {index}', 'callback_data':f'replace:{story.id}:1'},
            {'text':f'🔎 Sumber {index}', 'url':story.source_url},
        ])
    rows.append([{'text':'🔄 Ide Berita Lain',
                  'callback_data':f'nav:replacements:{draft.id}'}])
    return with_home_button({'inline_keyboard':rows})


def offer_replacements(db, rejected_draft, actor, bot, chat_id, *, discover_if_empty=True):
    """Offer multiple ideas with URLs, without spending any AI generation quota."""
    if rejected_draft.status != 'rejected':
        raise ValueError('Hanya berita yang ditolak dapat memperoleh pengganti.')
    options = available_replacements(db, rejected_draft, actor)
    if not options and discover_if_empty:
        # Pull official feeds only when the known eligible backlog is exhausted.
        from .research import discover, SOURCES, evergreen_sources
        for feeds in (SOURCES, evergreen_sources()):
            try:
                list(discover(db, sources=feeds))
                db.commit()
            except Exception:
                db.rollback()  # Never claim missing candidates imply bad facts.
                continue
            options = available_replacements(db, rejected_draft, actor)
            if options:
                break
    if options:
        for story in options:
            db.add(Audit(
                draft_id=story.id, event='replacement_offered', actor=str(actor),
                detail={'rejected_draft_id':rejected_draft.id,
                        'rejected_version':rejected_draft.version}
            ))
        db.commit()
        lines=['📰 PILIH BERITA PENGGANTI', '',
               'Berita sebelumnya ditolak dan tidak akan dipublikasikan.',
               'Pilih satu ide. AI baru membuat caption dan cover setelah Anda memilih; '
               'tidak perlu Approve.', '']
        for number, story in enumerate(options,1):
            lines.append(f'{number}. {clean_text(story.title, 150)}')
            lines.append(f'   Sumber: {clean_text(story.source_name,65)}'
                         f' • {clean_text(story.topic,28)}')
            lines.append('')
        lines.append('Pengganti boleh menambah jumlah berita di luar empat jadwal pembuatan rutin.')
    else:
        lines=['📰 Belum ada kandidat pengganti baru dari sumber resmi.',
               'Anda dapat mencoba Ide Berita Lain lagi. '
               'Artikel yang sudah ditolak atau pernah dijadikan draft tidak akan muncul kembali.']
    if bot:
        bot.message(chat_id, '\n'.join(lines), replacement_keyboard(rejected_draft, options))
    return options


def validate_selection(db, story_id, actor):
    """A selection must belong to a recent owner offer for a rejected draft."""
    from .automation_mode import current_mode, MANUAL_POST
    if current_mode(db)[0] != MANUAL_POST:
        raise ValueError('Pilihan pengganti hanya tersedia dalam mode Post Manual.')
    now = datetime.now(timezone.utc)
    offers = db.execute(select(Audit).where(
        Audit.event == 'replacement_offered',
        Audit.draft_id == story_id, Audit.actor == str(actor),
    ).order_by(Audit.id.desc()).limit(20)).scalars().all()
    valid = False
    for offer in offers:
        sent_at = offer.created_at
        if sent_at.tzinfo is None:
            sent_at = sent_at.replace(tzinfo=timezone.utc)
        old = db.get(Draft, (offer.detail or {}).get('rejected_draft_id'))
        if (now-sent_at <= timedelta(hours=48) and old
                and old.status == 'rejected'):
            valid = True
            break
    if not valid:
        raise ValueError('Pilihan pengganti kedaluwarsa. Minta ide berita baru.')
    story = db.get(Story, story_id)
    if (not story or story.verification_status != 'needs_fact_check'
            or not trusted_source(story.source_url)
            or db.execute(select(Draft.id).where(Draft.story_id == story_id)).first()):
        raise ValueError('Kandidat ini sudah diproses atau tidak tersedia. Pilih berita lain.')
    return story
