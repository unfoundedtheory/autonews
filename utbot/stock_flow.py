"""Inventory, early Telegram posting kits, and guarded 24-hour editorial fallback.

A missed Telegram approval never bypasses independent factual/style QC or the
photo-rights gate. Manual-music approvals and automatic silent-photo approvals
remain distinct PER DRAFT; the global Instagram mode is never flipped.
"""
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse
from sqlalchemy import select, func
from .models import Draft, Story, Audit
from .config import CONFIG

TIMEOUT = timedelta(hours=24)

def is_auto_approved(db, draft):
    """The persisted approval event is version-bound, not a mutable global flag."""
    events = db.execute(select(Audit.detail).where(
        Audit.draft_id == draft.id, Audit.event == 'auto_approved_24h'
    )).scalars().all()
    return any((d or {}).get('version') == draft.version for d in events)

def stock_to_prepare(db, config=CONFIG):
    """Never discard unsent drafts; only top up to a bounded editorial inventory."""
    active = db.execute(select(func.count(Draft.id)).where(
        Draft.status.in_(['pending_approval', 'approved']),
        Draft.publish_state.in_(['unpublished', 'manual_music_pending', 'awaiting_container'])
    )).scalar_one()
    target = max(1, min(int(config.draft_stock_target), 60))
    batch = max(1, min(int(config.prepare_batch_limit), 5))
    return max(0, min(batch, target - active))

def _commons_permissive_photo(draft):
    """Small, explicit auto-use allowlist; metadata is not blanket rights proof.

    CC BY/SA, unidentified creator, and arbitrary publisher image URLs require
    prior human rights review. Only Wikimedia-sourced PD/CC0 candidates qualify.
    """
    origin = urlparse(draft.source_image_url or '')
    page = urlparse(draft.media_page_url or '')
    license_name = (draft.photo_license or '').strip().casefold()
    allowed = {'cc0', 'public domain', 'pd-old', 'pd-usgov', 'pdm 1.0'}
    return (
        origin.scheme == 'https' and origin.hostname == 'upload.wikimedia.org'
        and page.scheme == 'https' and page.hostname == 'commons.wikimedia.org'
        and license_name in allowed
        and bool((draft.image_credit or '').strip())
    )

def _photo_auto_safe(draft):
    return bool(
        (draft.rights_reviewed or _commons_permissive_photo(draft))
        and (draft.image_credit or '').strip()
        and (draft.photo_license or '').strip()
        and (draft.image_url or '').startswith('https://')
    )

def _auto_enabled(config):
    return (
        config.auto_approve_24h and config.photo_music_mode == 'manual'
        and config.live_publish and bool(config.ig_user_id and config.ig_token)
        and bool(config.brand_logo and Path(config.brand_logo).is_file())
    )

def auto_approve_overdue(db, *, now=None, config=CONFIG, limit=5):
    """Approve only pending vN >=24h old with current passing independent QC.

    No AI-generated self-certification, no guess about an image's rights, no
    bypass for manual imports, and no accidental auto approval of already
    human-approved music drafts. Publication still uses the normal time slots.
    """
    if not _auto_enabled(config):
        return {'enabled': False, 'approved': [], 'blocked': []}
    from .quality_control import report_for_draft
    from .editorial import approve
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    query = select(Draft).where(
        Draft.status == 'pending_approval',
        Draft.publish_state == 'unpublished',
        Draft.updated_at <= now - TIMEOUT
    ).order_by(Draft.updated_at, Draft.id).limit(max(1, min(limit, 20)))
    if db.bind.dialect.name == 'postgresql':
        query = query.with_for_update(skip_locked=True)
    candidates = db.execute(query).scalars().all()
    approved, blocked = [], []
    for d in candidates:
        story = db.get(Story, d.story_id)
        if d.expires_at and d.expires_at <= now:
            blocked.append(d.id)
            continue
        if not story or story.verification_status != 'verified' or not _photo_auto_safe(d):
            blocked.append(d.id)
            continue
        # For auto approval, the latest *version-specific* QC must be real,
        # passed, and current. The normal one-click human legacy waiver is
        # deliberately not available here.
        qc = report_for_draft(db, d, story)
        if not qc['passed'] or qc.get('style_review') != 'passed':
            blocked.append(d.id)
            continue
        try:
            approve(db, d, 'system:24h_timeout')
        except (ValueError, RuntimeError):
            blocked.append(d.id)
            continue
        db.add(Audit(draft_id=d.id, event='auto_approved_24h',
                     actor='system:24h_timeout',
                     detail={'version': d.version,
                             'mode': 'instagram_photo_without_music',
                             'timeout_hours': 24}))
        approved.append(d.id)
    db.commit()
    return {'enabled': True, 'approved': approved, 'blocked': blocked}


def music_kit_sent(db, draft):
    events = db.execute(select(Audit.detail).where(
        Audit.draft_id == draft.id,
        Audit.event == 'manual_music_kit_sent'
    )).scalars().all()
    return any((row or {}).get('version') == draft.version for row in events)


def send_music_kit(db, draft, story, bot, chat_id, *, force=False):
    """Send cover/caption immediately after human approval (NOT an IG Draft API).

    Allows idempotent recovery via a button if a partial Telegram send failed.
    Published and silent-auto-approved posts can never get a music kit.
    """
    from .instagram import caption_text
    from .photo_music import manual_music_message, manual_music_caption
    if draft.status != 'approved' or draft.approved_version != draft.version:
        raise ValueError('Hanya berita yang disetujui dapat dikirim ke Instagram Drafts.')
    if is_auto_approved(db, draft):
        raise ValueError('Berita fallback otomatis tidak boleh dikirim sebagai draf musik.')
    if draft.publish_state not in ('unpublished', 'manual_music_pending'):
        raise ValueError('Berita ini sudah diproses; paket musik tidak dapat dikirim.')
    if music_kit_sent(db, draft) and not force:
        return {'kit': 'already_sent'}
    if not bot:
        raise ValueError('Bot Telegram tidak tersedia.')
    if not draft.image_url and draft.image_local_path:
        from .media import upload_public_jpeg
        draft.image_url = upload_public_jpeg(
            draft.image_local_path, f'{draft.id}/v{draft.version}.jpg')
        db.commit()
    if not (draft.image_url or '').startswith('https://'):
        raise ValueError('Cover HTTPS belum tersedia untuk paket Instagram.')
    # The actual cover is sent as a Telegram photo so the editor can save it.
    if hasattr(bot, 'photo'):
        bot.photo(chat_id, draft.image_url, '🖼 Cover 4:5 — simpan untuk Instagram Drafts')
    bot.message(chat_id, manual_music_message(draft, story))
    bot.message(chat_id, '📝 CAPTION SIAP SALIN\n\n' + manual_music_caption(draft))
    bot.message(chat_id,
                '📅 Sudah simpan sebagai Draft Instagram? Musik ditambahkan di '
                'aplikasi Instagram. Saat jadwal tiba bot akan mengingatkan. '
                'Jangan konfirmasi terbit sebelum benar-benar memublikasikan.',
                {'inline_keyboard': [[{
                    'text': '🎵 Konfirmasi Post Instagram',
                    'callback_data': f'musicdone:{draft.id}:{draft.version}'
                }], [{
                    'text': '🔁 Kirim Ulang Paket',
                    'callback_data': f'musickit:{draft.id}:{draft.version}'
                }]]})
    db.add(Audit(draft_id=draft.id,event='manual_music_kit_sent',
                 actor='telegram',detail={'version':draft.version}))
    db.commit()
    return {'kit': 'sent'}

def dispatch_approved_kits(db, bot, chat_id, *, limit=5):
    """Backfill already-approved pre-deployment drafts without duplicating kits."""
    if not bot or not chat_id or CONFIG.photo_music_mode != 'manual':
        return {'sent': [], 'failed': []}
    rows = db.execute(select(Draft).where(
        Draft.status == 'approved',
        Draft.approved_version == Draft.version,
        Draft.publish_state.in_(['unpublished', 'manual_music_pending'])
    ).order_by(Draft.approved_at, Draft.id).limit(30)).scalars().all()
    sent, failed = [], []
    for d in rows:
        if is_auto_approved(db, d) or music_kit_sent(db, d):
            continue
        try:
            send_music_kit(db, d, db.get(Story, d.story_id), bot, chat_id)
            sent.append(d.id)
        except (ValueError, RuntimeError, OSError) as exc:
            db.rollback()
            failed.append({'id':d.id, 'error_type':type(exc).__name__})
        if len(sent) + len(failed) >= limit:
            break
    return {'sent':sent, 'failed':failed}
