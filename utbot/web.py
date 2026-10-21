"""Webhooks/worker endpoints. Workers must run with encrypted secrets and on HTTPS."""
from datetime import datetime,timezone
from contextlib import asynccontextmanager
from hmac import compare_digest
import logging
from pathlib import Path
from uuid import UUID
from fastapi import FastAPI,Request,HTTPException,Depends
import httpx
from pydantic import BaseModel
from sqlalchemy import select,delete
from sqlalchemy.exc import IntegrityError
from .models import Session,init_db,Story,Draft,Audit,TelegramSession,TelegramUpdateReceipt
from .config import CONFIG
from .editorial import approve,revise,lint,evidence_ready
from .scheduler import schedule_approved,due,WIB
from .instagram import InstagramPublisher,caption_text
from .photo_music import manual_music_message,manual_music_caption,instagram_post_url
from .meta_delivery import publish_facebook_once
from .telegram import TelegramClient,keyboard,advanced_keyboard,send_preview,photo_keyboard,main_menu,home_button,with_home_button
from .telegram_ui import pending_page,approved_page,stories_page,photo_candidate_message,PENDING_PAGE_SIZE
from .research import discover,fingerprint
from .rewrite import rewrite
from .pipeline import prepare_batch
from .media import find_photos,intake_image,render_draft,upload_public_jpeg
from .automation_health import tracked_cron, automation_status

log=logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app):
    # Staging only. Real deployment uses schema migrations for production changes.
    # Never initialize disposable SQLite storage in a serverless environment.
    if not (__import__('os').environ.get('VERCEL') and CONFIG.database_url.startswith('sqlite')):
        init_db()
    yield

app=FastAPI(title='Unfounded Theory Automation',version='0.7.0',lifespan=lifespan)
from .meta_oauth import router as meta_oauth_router
app.include_router(meta_oauth_router)
from .planner import router as planner_router
app.include_router(planner_router)

def session():
    if __import__('os').environ.get('VERCEL') and CONFIG.database_url.startswith('sqlite'):
        raise HTTPException(503, 'Persistent PostgreSQL DATABASE_URL is required on Vercel')
    with Session() as db:
        yield db

def worker_auth(request:Request):
    provided=request.headers.get('x-worker-secret','')
    if not CONFIG.worker_secret or not compare_digest(provided,CONFIG.worker_secret):
        raise HTTPException(403,'Unauthorized')

def telegram_auth(request:Request):
    provided=request.headers.get('x-telegram-bot-api-secret-token','')
    if not CONFIG.telegram_secret or not compare_digest(provided,CONFIG.telegram_secret):
        raise HTTPException(403,'Invalid webhook secret')

def cron_auth(request: Request):
    """Vercel cron sends Authorization: Bearer CRON_SECRET."""
    import os
    token=os.getenv('CRON_SECRET', '')
    provided=request.headers.get('authorization', '')
    if not token or not compare_digest(provided, 'Bearer '+token):
        raise HTTPException(403, 'Invalid Vercel cron authorization')
    if CONFIG.database_url.startswith('sqlite'):
        raise HTTPException(503, 'Persistent database is required for scheduled jobs')

@app.get('/cron/discover', dependencies=[Depends(cron_auth)])
def cron_discover():
    """Discover candidates at approximately 01:00 WIB."""
    from .runner import do_discover
    return tracked_cron('discover',lambda: {'discovery':do_discover()})

@app.get('/cron/prepare', dependencies=[Depends(cron_auth)])
def cron_prepare():
    """Prepare a small editorial batch at approximately 03:00 WIB."""
    from .runner import do_prepare
    return tracked_cron('prepare',lambda: {'prepared':do_prepare()})

@app.get('/cron/prepare/afternoon', dependencies=[Depends(cron_auth)])
def cron_prepare_afternoon():
    """Second daily batch to grow the editorial stock without extra publishing."""
    from .runner import do_prepare
    return tracked_cron('prepare_afternoon',lambda: {'prepared':do_prepare()})

@app.get('/cron/prepare/morning', dependencies=[Depends(cron_auth)])
def cron_prepare_morning():
    """Third daily batch, at approximately 09:00 WIB."""
    from .runner import do_prepare
    return tracked_cron('prepare_morning',lambda: {'prepared':do_prepare()})


@app.get('/cron/prepare/evening', dependencies=[Depends(cron_auth)])
def cron_prepare_evening():
    """Fourth daily batch, at approximately 21:00 WIB."""
    from .runner import do_prepare
    return tracked_cron('prepare_evening',lambda: {'prepared':do_prepare()})


@app.get('/cron/tick/{slot}', dependencies=[Depends(cron_auth)])
def cron_tick(slot: str):
    """Publish only pre-approved eligible drafts around 06/12/18 WIB."""
    if slot not in ('morning','noon','evening'):
        raise HTTPException(404,'Invalid slot')
    from .runner import do_reschedule, do_publish
    # Publish overdue-approved items before rebuilding future slots; Hobby cron
    # can arrive up to 59 minutes after a slot begins.
    def run():
        publication=do_publish()
        scheduled=do_reschedule()
        return {'queued':len(scheduled),'publication':publication}
    return tracked_cron('tick_'+slot,run)

@app.get('/cron/maintenance', dependencies=[Depends(cron_auth)])
def cron_maintenance():
    """Daily maintenance on Vercel Hobby; posting ticks also review 24h eligibility."""
    from .runner import do_maintenance
    return tracked_cron('maintenance',do_maintenance)

@app.get('/health')
def health():return {'status':'ok','live_publish':CONFIG.live_publish}

@app.get('/internal/readiness', dependencies=[Depends(worker_auth)])
def readiness(db=Depends(session)):
    """Safe production-readiness report; never returns credentials or secrets."""
    import os
    from sqlalchemy import text
    from .ai_provider import PROVIDERS
    db.execute(text('SELECT 1'))
    configured_ai=[name for name,spec in PROVIDERS.items()
                   if spec.key_env and bool(os.getenv(spec.key_env,''))]
    checks={
        'database_reachable':True,
        'persistent_postgres':db.bind.dialect.name == 'postgresql',
        'telegram_bot':bool(CONFIG.telegram_token),
        'telegram_webhook_secret':bool(CONFIG.telegram_secret),
        'telegram_allowed_admin':bool(CONFIG.admin_ids),
        'telegram_destination':bool(CONFIG.chat_id),
        'ai_key_available':bool(configured_ai),
        'media_storage':bool(CONFIG.supabase_url and CONFIG.supabase_key),
        'instagram_credentials':bool(CONFIG.ig_user_id and CONFIG.ig_token),
        'facebook_page_configured':bool(CONFIG.facebook_page_id and CONFIG.facebook_page_token),
        'manual_photo_music':CONFIG.photo_music_mode=='manual',
        'worker_secret':bool(CONFIG.worker_secret),
        'flexible_space_first_renderer':True,
    }
    required=['database_reachable','persistent_postgres','telegram_bot',
              'telegram_webhook_secret','telegram_allowed_admin',
              'telegram_destination','ai_key_available','media_storage','worker_secret']
    if CONFIG.photo_music_mode=='off':
        required.append('instagram_credentials')
    if CONFIG.facebook_crosspost:
        required.append('facebook_page_configured')
    blockers=[key for key in required if not checks[key]]
    return {'ready_for_live':len(blockers)==0 and CONFIG.photo_music_mode=='off' and CONFIG.live_publish,
            'ready_for_manual_handoff':len(blockers)==0 and CONFIG.photo_music_mode=='manual',
            'live_publish_enabled':CONFIG.live_publish,
            'checks':checks,'configured_ai':configured_ai,'blockers':blockers,
            'photo_music_mode':CONFIG.photo_music_mode,
            'facebook_crosspost':CONFIG.facebook_crosspost,
            'note':'Native music needs Instagram app handoff. Configuration presence is not an external API permission test.'}

@app.get('/internal/ai/providers', dependencies=[Depends(worker_auth)])
def ai_providers_status():
    """Report configured AI providers without touching external APIs or leaking credentials."""
    import os
    from .ai_provider import PROVIDERS
    return {
        'default': os.getenv('AI_PROVIDER', 'gemini'),
        'draft': os.getenv('AI_DRAFT_PROVIDER') or os.getenv('AI_PROVIDER', 'gemini'),
        'rewrite': os.getenv('AI_REWRITE_PROVIDER') or os.getenv('AI_PROVIDER', 'gemini'),
        'fallback_enabled': os.getenv('AI_ENABLE_FALLBACK', 'false').lower() == 'true',
        'paid_fallback_enabled': os.getenv('AI_ALLOW_PAID_FALLBACK', 'false').lower() == 'true',
        'providers': [{'name': name, 'key_configured': bool(os.getenv(spec.key_env, ''))
                       if spec.key_env else False,
                       'local_only': spec.kind == 'ollama',
                       'possibly_billable': spec.possibly_billable}
                      for name, spec in PROVIDERS.items()],
        'note': 'Key configured is not an API connectivity or quota check. Ollama requires a locally running model.'
    }

@app.get('/internal/meta/connection', dependencies=[Depends(worker_auth)])
def meta_connection_check():
    """Read-only Page linkage check; never expose Meta tokens."""
    from .meta import MetaGraph
    configured={'instagram_id':bool(CONFIG.ig_user_id),
                'instagram_token':bool(CONFIG.ig_token),
                'facebook_page_id':bool(CONFIG.facebook_page_id),
                'facebook_page_token':bool(CONFIG.facebook_page_token)}
    out={'configured':configured,'photo_music':'manual_in_instagram_app',
         'facebook_crosspost':CONFIG.facebook_crosspost}
    if CONFIG.facebook_page_id and CONFIG.facebook_page_token:
        try:
            linked=MetaGraph(CONFIG.facebook_page_token,
                             CONFIG.facebook_graph_version).page_linkage(CONFIG.facebook_page_id)
            out['linked_page']=linked
            out['instagram_id_matches']=(
                linked['instagram_business_account_id']==CONFIG.ig_user_id
                if CONFIG.ig_user_id else None)
        except (ValueError,httpx.HTTPError) as exc:
            out['linkage_error_type']=type(exc).__name__
    return out


@app.post('/internal/ai/test', dependencies=[Depends(worker_auth)])
def ai_connectivity_test():
    """Authenticated, non-persistent Gemini probe; never publishes."""
    import os
    from .ai_provider import generate_json
    if not os.getenv('GEMINI_API_KEY'):
        raise HTTPException(503, 'Gemini key not configured')
    try:
        result = generate_json(
            'Return a JSON object with ok=true and label=UT_TEST.',
            {'purpose': 'connectivity check only'},
            provider='gemini', temperature=0.0)
    except httpx.HTTPStatusError as exc:
        log.warning('Gemini test upstream status %s', exc.response.status_code)
        raise HTTPException(502, {'connected': False, 'upstream_status': exc.response.status_code}) from None
    except (httpx.HTTPError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        log.warning('Gemini test failed: %s', type(exc).__name__)
        raise HTTPException(502, {'connected': False, 'error_type': type(exc).__name__}) from None
    if result.get('ok') is not True or result.get('label') != 'UT_TEST':
        raise HTTPException(502, {'connected': False, 'error_type': 'UnexpectedResponse'})
    return {'provider': 'gemini', 'connected': True, 'persisted': False, 'published': False}

def gemini_test_message():
    """Admin-only Gemini diagnostic without publishing or saving content."""
    import os
    from .ai_provider import generate_json, PROVIDERS, _model_for
    model = _model_for(PROVIDERS['gemini'], role='default', model=None)
    if not os.getenv('GEMINI_API_KEY'):
        return '❌ GEMINI_API_KEY belum dikonfigurasi.'
    try:
        response = generate_json('Return JSON with ok=true and label=UT_TEST.',
                                 {'purpose': 'connectivity check'}, provider='gemini',
                                 temperature=0.0)
        if response.get('ok') is True and response.get('label') == 'UT_TEST':
            return '✅ Gemini terhubung.\\nModel: '+model+'\\nJSON valid. Tidak ada posting dibuat.'
        return '❌ Respons Gemini tidak sesuai. Model: '+model
    except httpx.HTTPStatusError as exc:
        return '❌ Gemini gagal. Model: '+model+'\\nHTTP '+str(exc.response.status_code)
    except (httpx.HTTPError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        log.warning('Gemini Telegram test failed: %s', type(exc).__name__)
        return '❌ Gemini gagal. Model: '+model+'\\nError: '+type(exc).__name__

def generate_test_cover(db, bot, chat_id):
    """Explicit admin-only test: try one EXISTING pending draft, no new news required."""
    from .cover_recovery import recover_article_cover
    from .renderer import cover_fits
    drafts=db.execute(select(Draft).where(
        Draft.status=='pending_approval',Draft.image_url.is_(None))
        .order_by(Draft.created_at.desc()).limit(25)).scalars().all()
    ready=[d for d in drafts if cover_fits(d.highlight,CONFIG.font_path)]
    if not ready:
        return ('ℹ️ Tidak ada draf pending yang siap dibuatkan cover. '
                'Jika highlight masih terlalu panjang, buka Pending Approval dan '
                'gunakan Perbaiki Cover Otomatis lebih dahulu.')
    failures=[]
    for draft in ready[:3]:
        story=db.get(Story,draft.story_id)
        if not story:continue
        try:
            recover_article_cover(db,draft,story,actor='telegram_cover_test')
            db.commit()
            try:
                if bot:send_preview(bot,chat_id,draft,story)
            except (httpx.HTTPError,ValueError,RuntimeError) as exc:
                return ('⚠️ Cover sudah dibuat dan disimpan, tetapi preview Telegram gagal: '+
                        str(exc)[:180])
            return ('✅ Cover 4:5 dari sumber resmi berhasil dibuat untuk draf '+
                    draft.id[:8]+'. Preview dikirim. Kredit, lisensi dan hak penggunaan '
                    'tetap harus diverifikasi sebelum Approve.')
        except (httpx.HTTPError,ValueError,RuntimeError,OSError) as exc:
            db.rollback()
            failures.append(draft.id[:8]+': '+str(exc)[:110])
    return ('⚠️ Belum berhasil memulihkan cover. Diagnostik: '+
            (' | '.join(failures)[:500] if failures else 'Tidak ada foto sumber yang tersedia.')+
            ' Buka Pending Approval untuk melihat draf dan opsi Ganti Foto.')


def send_editor_preview(db, bot, chat_id, draft, story):
    """Keep an editable preview in Post Manual mode after every revision.

    New draft versions receive a fresh manual handoff audit only after Telegram
    accepts the preview. Regular approval mode stays unchanged.
    """
    if not bot:
        return
    from .automation_mode import current_mode, MANUAL_POST, manual_post_ready, deliver_manual_post_preview
    if (current_mode(db)[0] == MANUAL_POST and
        draft.publish_state == 'unpublished' and
        draft.status == 'pending_approval'):
        if manual_post_ready(db, draft):
            send_preview(bot, chat_id, draft, story, manual_post=True)
        else:
            deliver_manual_post_preview(db, draft, bot, chat_id)
    else:
        send_preview(bot, chat_id, draft, story)


def generate_news_now(db, bot, chat_id):
    """Create one real editorial draft from the production discovery queue, requiring approval."""
    from .research import discover, SOURCES, evergreen_sources

    def notify(d):
        if bot:
            from .automation_mode import current_mode, MANUAL_POST, deliver_manual_post_preview
            if current_mode(db)[0] == MANUAL_POST:
                deliver_manual_post_preview(db,d,bot,chat_id)
            else:
                send_preview(bot,chat_id,d,db.get(Story,d.story_id))

    def prepared(rows):
        return next((r for r in rows if r.get('status')=='prepared'),None)

    def result_message(done):
        if done.get('notify_error'):
            return '⚠️ Draf dibuat, tetapi preview Telegram gagal: '+str(done['notify_error'])[:300]
        if done.get('has_photo'):
            return '✅ Satu draf dan cover dibuat. Paket dikirim ke Telegram; belum diposting.'
        return ('⚠️ Draf dibuat, tetapi belum memiliki cover. '+
                str(done.get('photo_error') or 'Pilih foto dari menu Telegram.')[:400])

    # 1. Finish the unreviewed queue before consuming any more sources.
    results=prepare_batch(db,limit=3,notifier=notify)
    attempted=list(results)
    done=prepared(results)
    if done:return result_message(done)

    # 2. Fresh feeds are still useful, but their age no longer gates eligibility.
    normal=list(discover(db,sources=SOURCES))
    db.commit()
    if sum(int(f.get('inserted',0)) for f in normal):
        results=prepare_batch(db,limit=1,notifier=notify)
        attempted.extend(results)
        done=prepared(results)
        if done:return result_message(done)

    # 3. Bounded evergreen archive pass: astronomy, history and archaeology.
    # Never claim failure just because no article was published in the past 14 days.
    archived=list(discover(db,sources=evergreen_sources()))
    db.commit()
    if sum(int(f.get('inserted',0)) for f in archived):
        results=prepare_batch(db,limit=1,notifier=notify)
        done=prepared(results)
        if done:return result_message(done)

    failures_pending=[row for row in attempted if row.get('status')=='retry_pending']
    if failures_pending:
        # A failed API call or invalid draft is NOT an active background job.
        # Tell the owner what failed instead of falsely claiming AI is working.
        reasons=[]
        for row in failures_pending:
            label=row.get('reason','UnknownError')
            status=row.get('http_status')
            if status is not None:
                label+=f' (HTTP {status})'
            if label not in reasons:
                reasons.append(label)
        stages=[str(row.get('stage')) for row in failures_pending if row.get('stage')]
        stage_note=(' Tahap: '+', '.join(dict.fromkeys(stages[:3]))+'.') if stages else ''
        return ('⚠️ Kandidat berita ditemukan, tetapi pembuatan draft GAGAL '
                'pada percobaan ini ('+', '.join(reasons[:4])+').' + stage_note + ' '
                'Belum ada AI yang bekerja di latar belakang. Kandidat akan '
                'dicoba lagi pada jadwal otomatis berikutnya. '
                'Periksa konfigurasi provider AI/API dan log jika berulang.')
    checked=sum(f.get('seen',0) for f in normal+archived)
    duplicates=sum(f.get('duplicates',0) for f in normal+archived)
    failures=[f for f in normal if f.get('error')]
    healthy=[f for f in normal if not f.get('error')]
    details='; '.join(f"{f['feed']}: {str(f['error'])[:65]}" for f in failures)
    if failures and not healthy:
        return ('⚠️ Discovery: semua feed resmi bermasalah. '+details[:430]+
                ' Arsip juga diperiksa; tidak ada kandidat siap.')
    if failures:
        return (f'⚠️ Belum ada kandidat siap; {len(failures)} feed bermasalah dan '
                f'{len(healthy)} feed yang berhasil dibaca. '+
                details[:360]+' Arsip juga diperiksa.')
    return (f'ℹ️ {checked} artikel dari feed dan arsip diperiksa; {duplicates} sudah tersimpan. '
            'Belum ada kandidat berbeda yang dapat diproses. '
            'Coba lagi nanti ketika halaman arsip berganti atau periksa sumber dan QC.')

def generate_test_news(db, bot, chat_id):
    """Legacy test entrypoint; the Telegram UI invokes generate_news_now."""
    return generate_news_now(db, bot, chat_id)


class DraftInput(BaseModel):
    source_url:str;source_name:str;title:str;topic:str='astronomy'
    evidence:list[dict];highlight:str;caption:str;hashtags:list[str]
    image_url:str|None=None;image_credit:str|None=None;photo_license:str|None=None
    rights_reviewed:bool=False;facts_verified:bool=False;is_tragedy:bool=False

@app.post('/internal/import-draft',dependencies=[Depends(worker_auth)])
def import_draft(payload:DraftInput,db=Depends(session)):
    from .editorial import trusted_source
    if not trusted_source(payload.source_url):raise HTTPException(422,'Sumber primer harus tepercaya.')
    if db.execute(select(Story.id).where(Story.fingerprint==fingerprint(payload.source_url))).first():
        raise HTTPException(409,'This story already exists')
    story=Story(fingerprint=fingerprint(payload.source_url),title=payload.title,
        source_url=payload.source_url,source_name=payload.source_name,topic=payload.topic,
        evidence=payload.evidence,verification_status='verified' if payload.facts_verified else 'needs_fact_check')
    db.add(story);db.flush()
    d=Draft(story_id=story.id,highlight=payload.highlight,caption=payload.caption,
        hashtags=payload.hashtags,image_url=payload.image_url,image_credit=payload.image_credit,
        photo_license=payload.photo_license,rights_reviewed=payload.rights_reviewed,is_tragedy=payload.is_tragedy)
    db.add(d);db.commit()
    return {'story_id':story.id,'draft_id':d.id,'lint':lint(d.highlight,d.caption,d.hashtags),
            'ready_for_approval':evidence_ready(story) and story.verification_status=='verified' and bool(d.image_url or d.image_local_path)}

@app.post('/jobs/discover',dependencies=[Depends(worker_auth)])
def discover_job(db=Depends(session)):
    out=list(discover(db));db.commit()
    return {'feeds':out,'note':'Discovery creates unverified candidates only.'}

@app.post('/jobs/prepare',dependencies=[Depends(worker_auth)])
def prepare_job(db=Depends(session)):
    bot=TelegramClient(CONFIG.telegram_token) if CONFIG.telegram_token and CONFIG.chat_id else None
    def notify(d):
        if bot:send_preview(bot,CONFIG.chat_id,d,db.get(Story,d.story_id))
    items=prepare_batch(db,limit=3,notifier=notify)
    return {'items':items,'note':'Automated quote matching does not replace editor approval.'}

@app.get('/internal/drafts',dependencies=[Depends(worker_auth)])
def list_drafts(db=Depends(session)):
    ds=db.execute(select(Draft).order_by(Draft.created_at.desc()).limit(100)).scalars().all()
    return [{'id':d.id,'status':d.status,'version':d.version,'slot':d.scheduled_at,'highlight':d.highlight,
             'rights_reviewed':d.rights_reviewed,'has_render':bool(d.image_local_path)} for d in ds]

@app.post('/internal/notify/{draft_id}',dependencies=[Depends(worker_auth)])
def notify(draft_id:str,db=Depends(session)):
    d=db.get(Draft,draft_id)
    if not d:raise HTTPException(404,'Draft not found')
    if not (CONFIG.telegram_token and CONFIG.chat_id):raise HTTPException(503,'Telegram not configured')
    send_preview(TelegramClient(CONFIG.telegram_token),CONFIG.chat_id,d,db.get(Story,d.story_id))
    return {'sent':True}

def _bot():return TelegramClient(CONFIG.telegram_token) if CONFIG.telegram_token else None

def _revision_text(field,text,d,st):
    # Imperative sentences are instructions; a complete alternative text is used verbatim.
    start=text.casefold().strip()
    instruction=any(start.startswith(p) for p in ('ganti','buat ','perbaiki','persingkat','pendekkan','lebih ','ubah ','tulis ','tambahkan','hilangkan'))
    if field=='caption' and '\n\n' not in text:instruction=True
    if field=='highlight' and len(text)<45:instruction=True
    return rewrite(field,text,d,st) if instruction else text

def _replace_photo(db,d,url,uid,*,details=None):
    from .media import render_draft
    from .renderer import require_cover_fit
    require_cover_fit(d.highlight,CONFIG.font_path)
    src=Path(CONFIG.media_dir)/d.id/f'source_v{d.version+1}.jpg'
    photo_path=intake_image(url,str(src))
    revise(db,d,'source_image_url',url,uid)
    d.source_image_path=photo_path
    d.image_credit=(details or {}).get('credit') or None
    d.photo_license=(details or {}).get('license') or None
    d.image_license_url=(details or {}).get('license_url')
    d.media_page_url=(details or {}).get('page_url') or url
    d.photo_candidates=[]
    render_draft(d)

def _replace_telegram_photo(db,d,file_id,uid,bot):
    """Editor-supplied Telegram photo; license review and attribution still required."""
    from .media import render_draft
    from .renderer import require_cover_fit
    require_cover_fit(d.highlight,CONFIG.font_path)
    src=Path(CONFIG.media_dir)/d.id/f'source_v{d.version+1}.jpg'
    photo_path=bot.download_photo(file_id,str(src))
    revise(db,d,'source_image_url','telegram-upload:'+file_id,uid)
    d.source_image_path=photo_path
    d.media_page_url=None
    d.image_credit=None
    d.photo_license=None
    d.image_license_url=None
    d.photo_candidates=[]
    render_draft(d)

@app.post('/telegram/webhook',dependencies=[Depends(telegram_auth)])
def telegram_webhook(payload:dict,db=Depends(session)):
    bot=_bot(); cb=payload.get('callback_query');msg=payload.get('message')
    data=cb or msg or {}
    uid=int((data.get('from') or {}).get('id',0))
    if uid not in CONFIG.admin_ids:return {'ok':True,'ignored':'not_allowlisted'}
    chat_id=(msg or {}).get('chat',{}).get('id') or (cb or {}).get('message',{}).get('chat',{}).get('id')
    if not chat_id:return {'ok':True}
    # Telegram may replay the same update while Gemini/image generation is busy.
    # A committed unique receipt prevents duplicate preparation across workers.
    update_id=payload.get('update_id')
    if isinstance(update_id,int):
        try:
            db.add(TelegramUpdateReceipt(update_id=str(update_id)))
            db.commit()
        except IntegrityError:
            db.rollback()
            return {'ok':True,'ignored':'duplicate_telegram_update'}
    def send(s,menu=False,finished=False):
        if bot:bot.message(chat_id,s,main_menu() if menu else home_button() if finished else None)
    def show_pending(page=0):
        from sqlalchemy import func
        total=db.execute(select(func.count(Draft.id)).where(
            Draft.status=='pending_approval')).scalar_one()
        page=max(0,min(page,max(0,(total-1)//PENDING_PAGE_SIZE)))
        pending=db.execute(select(Draft).where(Draft.status=='pending_approval')
                   .order_by(Draft.created_at.desc(),Draft.id.desc())
                   .offset(page*PENDING_PAGE_SIZE).limit(PENDING_PAGE_SIZE)).scalars().all()
        if bot:
            body,actions=pending_page(pending,total,page)
            bot.message(chat_id,body,with_home_button(actions))
    def show_approved(page=0):
        from sqlalchemy import func
        active = (Draft.status == 'approved',
                  Draft.approved_version == Draft.version,
                  Draft.publish_state.in_(['unpublished', 'manual_music_pending',
                                            'awaiting_container']))
        total = db.execute(select(func.count(Draft.id)).where(*active)).scalar_one()
        page = max(0, min(page, max(0, (total-1)//PENDING_PAGE_SIZE)))
        drafts = db.execute(select(Draft).where(*active)
                    .order_by(Draft.approved_at.desc(), Draft.id.desc())
                    .offset(page*PENDING_PAGE_SIZE).limit(PENDING_PAGE_SIZE)).scalars().all()
        if bot:
            body, actions = approved_page(drafts, total, page)
            bot.message(chat_id, body, with_home_button(actions))

    def show_stories(page=0):
        from sqlalchemy import func
        total = db.execute(select(func.count(Story.id))).scalar_one()
        page = max(0, min(page, max(0, (total-1)//PENDING_PAGE_SIZE)))
        stories = db.execute(select(Story)
                    .order_by(Story.created_at.desc(), Story.id.desc())
                    .offset(page*PENDING_PAGE_SIZE).limit(PENDING_PAGE_SIZE)).scalars().all()
        if bot:
            body, actions = stories_page(stories, total, page)
            bot.message(chat_id, body, actions)

    if cb and str(cb.get('data','')).startswith('nav:'):
        action = cb['data'][4:]
        if action in ('test_gemini', 'test_news', 'test_cover'):
            # Old Telegram messages cannot be retroactively erased without their IDs.
            # Disable legacy actions and replace the clicked message's obsolete keyboard.
            if bot:
                bot.answer(cb.get('id'), 'Tombol percobaan lama sudah dinonaktifkan.')
                old_message = cb.get('message') or {}
                if hasattr(bot, 'call') and isinstance(old_message.get('message_id'), int):
                    try:
                        bot.call('editMessageReplyMarkup', {
                            'chat_id':chat_id,
                            'message_id':old_message['message_id'],
                            'reply_markup':main_menu(),
                        })
                    except (httpx.HTTPError, RuntimeError, ValueError):
                        log.warning('Could not refresh legacy Telegram keyboard')
            send('ℹ️ Menu percobaan sudah diganti. Gunakan menu operasional berikut.', True)
            return {'ok':True, 'deprecated_menu':action}
        if action in ('mode:approval','mode:full_auto','mode:manual_post'):
            from .automation_mode import current_mode,set_mode
            target=action.partition(':')[2]
            current,_=current_mode(db)
            if target==current:
                send('✅ Mode ini sudah aktif.')
                if bot:bot.answer(cb.get('id'),'Mode tidak berubah')
                return {'ok':True,'automation_mode':current}
            if target=='manual_post':
                set_mode(db,'manual_post',uid)
                send('✅ POST MANUAL aktif. Semua berita BARU yang selesai dibuat dikirim tanpa Approve. Tidak ada publikasi otomatis Instagram/Facebook.')
                return {'ok':True,'automation_mode':'manual_post'}
            if target=='full_auto':
                if not (CONFIG.live_publish and CONFIG.photo_music_mode=='off'):
                    send('⚠️ Full Otomatis membutuhkan Instagram live publish aktif '
                         'dan mode foto tanpa musik. Konfigurasi server belum siap.')
                    return {'ok':True,'automation_mode':'unavailable'}
                if bot:
                    bot.message(chat_id,
                        '⚠️ Aktifkan FULL OTOMATIS? Berita BARU yang lolos QC independen, '
                        'verifikasi sumber, dan hak foto akan disetujui serta '
                        'diposting otomatis sesuai jadwal tanpa Approve. '
                        'Draft lama tidak otomatis dipublikasikan. '
                        'Konten yang gagal QC atau izin foto tetap ditahan.',
                        with_home_button({'inline_keyboard':[
                            [{'text':'✅ Ya, Aktifkan Full Otomatis',
                              'callback_data':'nav:mode_confirm:full_auto'}],
                            [{'text':'↩️ Batal','callback_data':'nav:status'}]]}))
                return {'ok':True,'automation_mode':'confirmation_required'}
            set_mode(db,'approval',uid)
            send('✅ Mode DENGAN APPROVAL aktif. Draft berikutnya menunggu '
                 'persetujuan Anda sebelum dijadwalkan atau diposting.')
            return {'ok':True,'automation_mode':'approval'}
        if action=='mode_confirm:full_auto':
            from .automation_mode import set_mode
            if not (CONFIG.live_publish and CONFIG.photo_music_mode=='off'):
                send('⚠️ Full Otomatis tidak tersedia karena konfigurasi Instagram.')
                return {'ok':True,'automation_mode':'unavailable'}
            set_mode(db,'full_auto',uid)
            send('✅ FULL OTOMATIS aktif untuk berita BARU. '
                 'Hanya draft yang lolos QC, sumber, dan izin foto '
                 'yang akan dijadwalkan dan diposting tanpa Approve.')
            if bot:bot.answer(cb.get('id'),'Full Otomatis aktif')
            return {'ok':True,'automation_mode':'full_auto'}
        if action.startswith('replacements:'):
            from .automation_mode import current_mode, MANUAL_POST
            from .replacements import offer_replacements
            if current_mode(db)[0]!=MANUAL_POST:
                send('Penggantian tanpa approval hanya tersedia di Post Manual.')
                return {'ok':True,'replacement':'mode_unavailable'}
            try:
                rejected_id=action.partition(':')[2]
                UUID(rejected_id)
                old=db.get(Draft,rejected_id)
                if not old or old.status!='rejected':
                    raise ValueError('Berita yang ditolak tidak tersedia.')
                options=offer_replacements(db,old,uid,bot,chat_id)
                return {'ok':True,'replacement_choices':len(options)}
            except (ValueError,RuntimeError,httpx.HTTPError,OSError) as exc:
                db.rollback()
                send('⚠️ Ide pengganti belum tersedia: '+str(exc)[:220])
                return {'ok':True,'replacement':'error'}
        if action == 'generate_now':
            if bot:bot.answer(cb.get('id'),'Menyiapkan berita')
            send('📰 Menyiapkan berita dari sumber resmi…')
            try:
                response = generate_news_now(db,bot,chat_id)
            except (ValueError,RuntimeError,httpx.HTTPError,OSError) as exc:
                db.rollback()
                log.warning('Generate news failed: %s',type(exc).__name__)
                response = '⚠️ Proses gagal: '+type(exc).__name__+'. Periksa Status Otomasi.'
            if bot:bot.message(chat_id,response,home_button())
            return {'ok':True,'menu':'generate_now'}
        if action == 'decline_all':
            from sqlalchemy import func
            total = db.execute(select(func.count(Draft.id)).where(
                Draft.status == 'pending_approval')).scalar_one()
            if not total:
                send('✅ Tidak ada draft pending yang perlu ditolak.')
            elif bot:
                bot.message(chat_id, f'⚠️ Tolak SEMUA {total} draft Pending Approval?\\n'
                            'Tindakan ini tidak dapat dibatalkan lewat tombol. '
                            'Draft approved dan published tidak akan diubah.',
                            with_home_button({'inline_keyboard':[
                                [{'text':'✅ Yes, Decline All',
                                  'callback_data':f'nav:decline_confirm:{total}'}],
                                [{'text':'↩️ No, Batal','callback_data':'nav:decline_cancel'}]]}))
            if bot:bot.answer(cb.get('id'),'Konfirmasi diperlukan')
            return {'ok':True,'confirm_decline_all':total}
        if action == 'decline_cancel':
            if bot:bot.answer(cb.get('id'),'Dibatalkan')
            show_pending()
            return {'ok':True,'decline_cancelled':True}
        if action.startswith('decline_confirm:'):
            expected = action.partition(':')[2]
            if not expected.isascii() or not expected.isdigit() or len(expected)>8:
                if bot:bot.answer(cb.get('id'),'Konfirmasi tidak valid')
                return {'ok':True,'invalid_confirmation':True}
            pending = db.execute(select(Draft).where(
                Draft.status == 'pending_approval')).scalars().all()
            if len(pending) != int(expected) or not pending:
                if bot:bot.answer(cb.get('id'),'Daftar pending berubah')
                send('⚠️ Jumlah draft pending berubah. Konfirmasi ulang diperlukan.')
                show_pending()
                return {'ok':True,'confirmation_expired':True}
            for draft in pending:
                draft.status = 'rejected'
                draft.approved_at = None
                draft.approved_by = None
                draft.approved_version = None
                draft.scheduled_at = None
                db.add(Audit(draft_id=draft.id,event='bulk_decline',
                             actor=str(uid),detail={'source':'telegram_confirmed'}))
            db.commit()
            if bot:
                bot.answer(cb.get('id'),'Semua draft pending ditolak')
            send(f'✅ {len(pending)} draft Pending Approval ditolak. '
                 'Draft approved dan published tetap aman.',True)
            return {'ok':True,'declined':len(pending)}
        page = 0
        for section in ('pending', 'approved', 'stories'):
            if action.startswith(section+':'):
                page_text = action.partition(':')[2]
                if not page_text.isascii() or not page_text.isdigit() or len(page_text)>5:
                    if bot:
                        bot.answer(cb.get('id'), 'Halaman tidak valid')
                    return {'ok':True, 'invalid_page':True}
                page = int(page_text)
                action = section
                break
        if action not in ('home','pending','approved','stories','queue','status'):
            if bot:bot.answer(cb.get('id'),'Menu tidak valid')
            return {'ok':True}
        if action=='home':
            send('🛰 Unfounded Theory Newsroom\nPilih menu operasional di bawah.', True)
        elif action=='status':
            from sqlalchemy import func
            groups=db.execute(select(Draft.status,func.count(Draft.id)).group_by(Draft.status)).all()
            from .automation_mode import current_mode
            mode,_=current_mode(db)
            status_text=('🔵 POST MANUAL: berita dibuat otomatis dan dikirim tanpa Approve; Anda menerbitkannya sendiri.'
                         if mode=='manual_post' else '🟢 FULL OTOMATIS: berita baru yang lolos QC dan izin foto '
                         'langsung masuk jadwal posting tanpa Approve.'
                         if mode=='full_auto' else
                         '🟡 DENGAN APPROVAL: draft menunggu Approve dari Anda.')
            if bot:
                bot.message(chat_id,'⚙️ KONFIGURASI OTOMASI\\n'+status_text+
                    '\\n\\n📊 Status redaksi\\n'+
                    ('\\n'.join(f'{s}: {n}' for s,n in groups) or 'Belum ada berita')+
                    '\\n\\n'+automation_status(db),
                    with_home_button({'inline_keyboard':[
                        [{'text':('✅ ' if mode=='full_auto' else '')+'🤖 Full Otomatis',
                          'callback_data':'nav:mode:full_auto'}],
                        [{'text':('✅ ' if mode=='manual_post' else '')+'📤 Post Manual',
                          'callback_data':'nav:mode:manual_post'}],
                        [{'text':('✅ ' if mode=='approval' else '')+'👤 Dengan Approval',
                          'callback_data':'nav:mode:approval'}]]}))
        elif action=='pending':
            show_pending(page)
        elif action=='approved':
            show_approved(page)
        elif action=='stories':
            show_stories(page)
        elif action=='queue':
            now_utc=datetime.now(timezone.utc)
            # Keep overdue entries visible instead of concealing them just
            # because their immutable approved slot is already in the past.
            rows=db.execute(select(Draft).where(
                Draft.status=='approved',
                Draft.approved_version==Draft.version,
                Draft.publish_state.in_(['unpublished','awaiting_container','manual_music_pending']),
                Draft.scheduled_at.is_not(None))
                .order_by(Draft.scheduled_at).limit(15)).scalars().all()
            def describe_scheduled(d):
                at=d.scheduled_at
                at=at.replace(tzinfo=timezone.utc) if at.tzinfo is None else at
                suffix=(' ⚠️ TERLAMBAT / BELUM TERBIT' if at<=now_utc
                        else ' • terjadwal')
                if d.publish_state=='manual_music_pending':
                    suffix=' 🎵 Menunggu konfirmasi posting manual'
                return f'{at.astimezone(WIB):%d/%m %H:%M} - {d.highlight}{suffix}'
            message='📅 Jadwal WIB (waktu approval tidak otomatis digeser)\n'+(
                '\n'.join(f'{i+1}. {describe_scheduled(d)}' for i,d in enumerate(rows))
                or 'Belum ada antrean')
            eligible=[]
            if CONFIG.photo_music_mode=='off' and CONFIG.live_publish:
                for i,d in enumerate(rows):
                    if d.publish_state!='unpublished':
                        continue
                    consent=db.execute(select(Audit.detail).where(
                        Audit.draft_id==d.id,Audit.event=='photo_only_approved'
                    )).scalars().all()
                    if any((entry or {}).get('version')==d.version for entry in consent):
                        eligible.append([{'text':f'📸 Post Sekarang #{i+1}',
                                          'callback_data':f'postnow:{d.id}:{d.version}'}])
            if bot:bot.message(chat_id,message,
                with_home_button({'inline_keyboard':eligible}))
        if bot:bot.answer(cb.get('id'),'Diperbarui')
        return {'ok':True,'menu':action}
    if cb:
        cb_id=cb.get('id')
        try:
            action,ident,v=cb.get('data','').split(':',2)
            version=int(v);UUID(ident)
        except (TypeError,ValueError):
            if bot:bot.answer(cb_id,'Tombol tidak valid')
            return {'ok':True}
        d=db.get(Draft,ident) if action!='replace' else None
        if action!='replace' and (not d or d.version!=version):
            if bot:bot.answer(cb_id,'Versi lama, buka draf terbaru')
            return {'ok':True,'stale':True}
        st=db.get(Story,d.story_id) if d else None
        from .automation_mode import manual_post_ready
        def preview_current():
            send_editor_preview(db,bot,chat_id,d,st)
        try:
            if action=='open':
                from .automation_mode import manual_post_ready
                preview_current()
            elif action=='replace':
                from .replacements import validate_selection, offer_replacements
                from .pipeline import prepare_story
                from .automation_mode import deliver_manual_post_preview
                if bot:bot.answer(cb_id,'Membuat berita pilihan')
                try:
                    selected=validate_selection(db,ident,uid)
                    prior=db.execute(select(Audit).where(
                        Audit.event=='replacement_offered',Audit.draft_id==selected.id,
                        Audit.actor==str(uid)).order_by(Audit.id.desc()).limit(1)).scalar_one_or_none()
                    old_id=(prior.detail or {}).get('rejected_draft_id') if prior else None
                    send('📰 Membuat berita pengganti pilihan Anda dari sumber resmi. '
                         'AI memeriksa fakta, caption, dan cover sebelum mengirim preview.')
                    new_draft=prepare_story(db,selected)
                    db.add(Audit(draft_id=new_draft.id,event='replacement_prepared',actor=str(uid),
                                 detail={'source_story_id':selected.id,'replaced_draft_id':old_id}))
                    db.commit()
                    send_editor_preview(db,bot,chat_id,new_draft,selected)
                    send('✅ Draft pengganti berhasil dibuat. Anda dapat mengedit atau '
                         'memposting sendiri tanpa approval.',finished=True)
                    return {'ok':True,'replacement':'prepared','draft_id':new_draft.id}
                except (ValueError,RuntimeError,httpx.HTTPError,OSError) as exc:
                    db.rollback()
                    send('⚠️ Kandidat pengganti ini belum berhasil dibuat ('+
                         type(exc).__name__+'). Anda dapat memilih ide lain.',
                         finished=True)
                    return {'ok':True,'replacement':'failed'}
            elif action=='manualdone':
                from .automation_mode import manual_post_ready
                if not manual_post_ready(db,d) or d.publish_state!='unpublished':
                    raise ValueError('Berita ini bukan paket post manual aktif.')
                prior=db.get(TelegramSession,str(uid))
                if prior:db.delete(prior);db.flush()
                db.add(TelegramSession(user_id=str(uid),draft_id=d.id,mode='manual_post_link',version=d.version))
                db.commit()
                send('Kirim tautan posting Instagram https://www.instagram.com/p/... setelah Anda menerbitkannya.')
                return {'ok':True,'manual_post':'awaiting_link'}
            elif action=='more':
                if bot:bot.message(chat_id,'⋯ Opsi lanjutan untuk draf ini:',with_home_button(advanced_keyboard(d)))
            elif action=='actions':
                if bot:
                    from .telegram import manual_post_keyboard
                    bot.message(chat_id,'Pilih tindakan untuk draf:',manual_post_keyboard(d) if manual_post_ready(db,d) else with_home_button(keyboard(d)))
            elif action in ('retryig','postnow'):
                # Explicit owner request to retry an already-approved photo.
                # The persisted consent event prevents old manual-music drafts
                # from being silently republished after switching modes.
                if (CONFIG.photo_music_mode!='off' or not CONFIG.live_publish or
                    d.status!='approved' or d.approved_version!=d.version or
                    d.publish_state!='unpublished'):
                    raise ValueError('Posting langsung hanya tersedia untuk draft foto '
                                     'yang disetujui dan belum diproses.')
                approvals=db.execute(select(Audit.detail).where(
                    Audit.draft_id==d.id,Audit.event=='photo_only_approved')).scalars().all()
                if not any((entry or {}).get('version')==d.version for entry in approvals):
                    raise ValueError('Draft ini disetujui dalam mode lama. '
                                     'Jangan posting otomatis tanpa approval foto baru.')
                d.rights_reviewed=True
                # An explicit Post Sekarang request overrides a future posting slot.
                # The publisher still enforces approved version and unpublished state.
                d.scheduled_at=datetime.now(timezone.utc)
                db.add(Audit(draft_id=d.id,event='photo_post_retry_requested',
                             actor=str(uid),detail={'version':d.version}))
                db.commit()
                if bot:bot.answer(cb_id,'Mencoba publikasi foto')
                send('📸 Memeriksa kembali publikasi foto yang sudah disetujui…')
                try:
                    outcome=publish_job(db=db,target_draft_id=d.id)
                except HTTPException as err:
                    send('⚠️ Belum berhasil: '+str(err.detail)[:250],finished=True)
                else:
                    if outcome.get('published'):
                        send('✅ Foto berhasil terbit di Instagram. Media ID: '+
                             str(outcome.get('instagram_media_id')),finished=True)
                    elif outcome.get('waiting'):
                        send('⏳ Instagram masih memproses foto. Cron akan melanjutkan.',finished=True)
                    else:
                        issue=outcome.get('error') or outcome.get('note') or (
                            'Tidak ada draft yang memenuhi syarat posting.'
                            if outcome.get('due')==0 else outcome.get('status')) or 'Cek status koneksi Meta.'
                        send('⚠️ Belum terbit. Alasan: '+str(issue)[:250],finished=True)
                return {'ok':True,'instagram_retry':True}
            elif action=='hookideas':
                if d.status in ('published','rejected') or d.publish_state in ('publishing','published','uncertain'):
                    raise ValueError('Draf ini tidak boleh direvisi.')
                if bot:bot.answer(cb_id,'Menyusun alternatif hook')
                from .hook_editor import alternatives
                ideas=alternatives(d,st)
                db.add(Audit(draft_id=d.id,event='hook_candidates',actor=str(uid),
                             detail={'version':d.version,'options':ideas}))
                # A free-text reply to the suggested options is the editor's
                # own hook, NOT an instruction for the AI to rewrite.
                existing=db.get(TelegramSession,str(uid))
                if existing:db.delete(existing);db.flush()
                db.add(TelegramSession(user_id=str(uid),draft_id=d.id,
                                       mode='manual_hook',version=d.version))
                db.commit()
                rows=[[{'text':f'Pilih Hook {i+1}','callback_data':f'pickh{i}:{d.id}:{d.version}'}]
                      for i in range(len(ideas))]
                rows.append([{'text':'✍️ Tulis Hook Sendiri',
                              'callback_data':f'manualhook:{d.id}:{d.version}'}])
                rows.append([{'text':'↩️ Kembali ke Preview',
                              'callback_data':f'open:{d.id}:{d.version}'}])
                if bot:
                    bot.message(chat_id,
                        '✨ Alternatif hook dari sumber yang sama:\n\n'+
                        '\n\n'.join(f'{i+1}. {h}' for i,h in enumerate(ideas))+
                        '\n\nPilih salah satu, atau LANGSUNG ketik hook buatan Anda '
                        'sebagai pesan baru. Teks Anda tidak akan diubah AI. '
                        'Semua tetap melalui QC editorial. /cancel untuk batal.',
                        {'inline_keyboard':rows})
            elif action=='boostfont':
                if (d.status not in ('pending_approval','approved') or
                    d.publish_state!='unpublished'):
                    raise ValueError('Berita ini tidak bisa direvisi.')
                from .renderer import headline_font_size
                from .hook_editor import cover_fit_alternative
                from .quality_control import run_draft_qc
                old_size=headline_font_size(d.highlight,CONFIG.font_path)
                candidate=cover_fit_alternative(d,st)
                new_size=headline_font_size(candidate,CONFIG.font_path)
                if new_size<=old_size:
                    raise ValueError('Belum ditemukan versi yang lebih besar tanpa mengubah fakta.')
                revise(db,d,'highlight',candidate,uid)
                from .manual_hook import accent_for_hook
                d.accent_words=accent_for_hook(candidate,d.accent_words)
                if d.source_image_url or d.source_image_path:
                    render_draft(d)
                result=run_draft_qc(db,d,st,trigger='telegram_font_boost')
                db.add(Audit(draft_id=d.id,event='cover_font_boosted',actor=str(uid),
                             detail={'version':d.version,'previous_px':old_size,
                                     'current_px':new_size,'qc_passed':bool(result.get('passed'))}))
                db.commit()
                preview_current()
                send(f'🔠 Ukuran font naik dari {old_size}px menjadi {new_size}px. '
                     'Headline diringkas berdasarkan evidence resmi. Periksa ulang '
                     'caption, visual, dan hasil QC sebelum posting manual.')
            elif action=='redesign':
                if d.status not in ('pending_approval','approved') or d.publish_state in ('publishing','uncertain','published','awaiting_container'):
                    raise ValueError('Cover tidak dapat diubah saat publikasi atau setelah terbit.')
                if not d.source_image_url:
                    raise ValueError('Sumber foto tidak tersedia. Gunakan Ganti Foto atau Cari Ulang Cover.')
                from .renderer import require_cover_fit
                require_cover_fit(d.highlight,CONFIG.font_path)
                # Allocate a NEW immutable URL: Supabase disallows overwriting
                # old vN jpg objects. Old approval is revoked.
                revise(db,d,'highlight',d.highlight,uid)
                render_draft(d)
                d.last_error=None
                db.add(Audit(draft_id=d.id,event='cover_design_updated',actor=str(uid),
                             detail={'version':d.version,'note':'new scalable typography'}))
                db.commit()
                preview_current()
                send('🎨 Cover sudah dibuat ulang dengan font headline terbaru. '
                     'Periksa preview hasil revisi dan hasil QC. '
                     'jalankan Hasil QC, lalu Approve versi baru.')
            elif action=='autofit':
                if d.status!='pending_approval' or d.publish_state in ('publishing','uncertain','published'):
                    raise ValueError('Hanya draf pending yang boleh diperbaiki.')
                from .hook_editor import cover_fit_alternative
                from .renderer import require_cover_fit
                if bot:bot.answer(cb_id,'Mencari hook yang memaksimalkan ruang cover')
                replacement=cover_fit_alternative(d,st)
                require_cover_fit(replacement,CONFIG.font_path)
                original=d.highlight
                revise(db,d,'highlight',replacement,uid)
                from .manual_hook import accent_for_hook
                d.accent_words=accent_for_hook(replacement,d.accent_words)
                d.last_error=None
                db.add(Audit(draft_id=d.id,event='cover_hook_auto_revised',actor=str(uid),
                             detail={'version':d.version,'original':original,
                                     'replacement':replacement,'review_required':True}))
                if d.source_image_url or d.source_image_path:
                    try:
                        render_draft(d)
                    except (ValueError,RuntimeError,httpx.HTTPError,OSError) as exc:
                        d.image_url=None
                        d.image_local_path=None
                        d.last_error='Cover belum tersedia: '+str(exc)[:160]
                db.commit()
                preview_current()
                send('✨ Highlight telah diperbaiki dan tetap memerlukan persetujuan Anda. '+
                     ('Cover siap diperiksa.' if d.image_url or d.image_local_path else
                      'Pilih Cari Ulang Cover untuk melengkapi gambarnya.'))
            elif action=='retrycover':
                if d.status!='pending_approval' or d.publish_state in ('publishing','uncertain','published'):
                    raise ValueError('Hanya draf yang belum disetujui dapat mencari ulang cover.')
                from .renderer import require_cover_fit
                require_cover_fit(d.highlight,CONFIG.font_path)
                if bot:bot.answer(cb_id,'Mencari foto dari artikel resmi')
                from .cover_recovery import recover_article_cover
                try:
                    recover_article_cover(db,d,st,actor=uid)
                    db.commit()
                    preview_current()
                    send('🖼 Cover 4:5 berhasil dibuat dari artikel resmi. '
                         'Isi kredit dan lisensi foto, lalu lakukan Verifikasi Hak Foto sebelum Approve.')
                    return {'ok':True,'cover':'official_article'}
                except (ValueError,RuntimeError,httpx.HTTPError,OSError) as hero_error:
                    db.rollback()
                    d=db.get(Draft,ident)
                    send('ℹ️ Foto utama artikel belum bisa dipakai: '+str(hero_error)[:150]+
                         '. Mencari alternatif Wikimedia yang berlisensi.')
                from .photo_relevance import search_queries,photo_subject_match
                from .media import find_photos
                choices=[]
                visited=set()
                errors=[]
                for term in search_queries(st.title,story_title=st.title):
                    try:
                        candidates=find_photos(term,limit=6)
                    except (httpx.HTTPError,ValueError) as exc:
                        errors.append(type(exc).__name__)
                        continue
                    for candidate in candidates:
                        identity=candidate.get('page_url') or candidate.get('image_url')
                        if identity and identity not in visited and photo_subject_match(term,candidate,st.title):
                            visited.add(identity)
                            choices.append(candidate)
                    if choices:break
                if not choices:
                    send('⚠️ Kandidat cover yang cocok dan berlisensi belum ditemukan.'+
                         (' Kendala pencarian: '+', '.join(errors) if errors else '')+
                         ' Gunakan Ganti Foto untuk mengunggah foto yang haknya sudah Anda periksa.')
                else:
                    d.photo_candidates=choices[:6]
                    db.commit()
                    if bot:
                        lines=['🔎 Pilih satu kandidat cover. Identitas foto dan lisensinya harus diperiksa lagi.']
                        lines.extend(str(i+1)+'. '+str(item.get('title') or 'Tanpa judul')[:100]+
                           ' | '+str(item.get('license') or 'Lisensi belum jelas')
                           for i,item in enumerate(d.photo_candidates))
                        bot.message(chat_id,photo_candidate_message(d),photo_keyboard(d))
            elif action.startswith('pickh') and action[5:].isdigit():
                index=int(action[5:])
                report=db.query(Audit).filter(Audit.draft_id==d.id,
                            Audit.event=='hook_candidates').order_by(Audit.id.desc()).first()
                choices=(report.detail or {}).get('options',[]) if report and (report.detail or {}).get('version')==d.version else []
                if index>=len(choices):raise ValueError('Opsi hook kedaluwarsa. Buat ulang alternatif.')
                from .renderer import require_cover_fit
                require_cover_fit(choices[index],CONFIG.font_path)
                revise(db,d,'highlight',choices[index],uid)
                editing=db.get(TelegramSession,str(uid))
                if editing:db.delete(editing)
                from .manual_hook import accent_for_hook
                d.accent_words=accent_for_hook(choices[index],d.accent_words)
                db.add(Audit(draft_id=d.id,event='hook_selected',actor=str(uid),
                             detail={'version':d.version,'source_version':version,'choice':index+1}))
                if d.source_image_url or d.source_image_path:
                    render_draft(d)
                db.commit()
                preview_current()
                send('✨ Hook diperbarui. QC dan approval harus diperiksa lagi.')
            elif action=='qc':
                from .quality_control import report_for_draft,run_draft_qc
                if bot:bot.answer(cb_id,'Memeriksa SOP editorial terbaru')
                previous=report_for_draft(db,d,st)
                if previous['passed']:
                    report=previous
                else:
                    report=run_draft_qc(db,d,st)
                    db.commit()
                send(format_editorial_qc(d,report))
            elif action=='musickit':
                from .stock_flow import send_music_kit, is_auto_approved
                if (d.status!='approved' or is_auto_approved(db,d)
                    or d.publish_state not in ('unpublished','manual_music_pending')):
                    raise ValueError('Paket musik hanya untuk berita yang disetujui secara manual.')
                send_music_kit(db,d,st,bot,chat_id,force=True)
                send('📦 Paket Instagram Drafts dikirim ulang. Simpan foto dan caption, lalu pilih musik di Instagram.')
            elif action=='musicdone':
                from .stock_flow import music_kit_sent, is_auto_approved
                if (d.status!='approved'
                    or is_auto_approved(db,d)
                    or not (d.publish_state=='manual_music_pending' or
                            (d.publish_state=='unpublished' and music_kit_sent(db,d)))):
                    raise ValueError('Belum ada kiriman musik manual yang menunggu konfirmasi.')
                prior=db.get(TelegramSession,str(uid))
                if prior:db.delete(prior);db.flush()
                db.add(TelegramSession(user_id=str(uid),draft_id=d.id,
                                       mode='music_post_link',version=d.version))
                db.commit()
                send('🎵 Kirim tautan posting Instagram yang benar-benar sudah terbit '
                     'dengan musik, format https://www.instagram.com/p/KODE/. '
                     'Bot akan mencatat konfirmasi Anda dan tidak akan memposting ulang. '
                     'Ketik /cancel jika belum selesai.')
            elif action=='musiccancel':
                from .stock_flow import music_kit_sent, is_auto_approved
                if (d.status!='approved' or is_auto_approved(db,d) or
                    not (d.publish_state=='manual_music_pending' or
                         (d.publish_state=='unpublished' and music_kit_sent(db,d)))):
                    raise ValueError('Hanya handoff yang belum dikonfirmasi dapat dibatalkan.')
                d.publish_state='unpublished'
                d.version+=1
                d.status='pending_approval'
                d.approved_version=None
                d.approved_by=None
                d.approved_at=None
                d.scheduled_at=None
                db.add(Audit(draft_id=d.id,event='manual_music_cancelled',
                             actor=str(uid),detail={'version':d.version}))
                db.commit()
                send('↩️ Handoff dibatalkan. Draf kembali ke Pending Approval. '
                     'Periksa apakah posting sudah terbit di Instagram sebelum menyetujui ulang.')
            elif action=='approve':
                if d.status=='approved' and d.approved_version==d.version:
                    # A previous preview keyboard may still have an Approve
                    # button. Reply with a Telegram toast, NEVER a new message.
                    # Repeated taps do not re-schedule, re-notify, or post.
                    if bot:bot.answer(cb_id,'✅ Sudah dijadwalkan; tidak ada perubahan.')
                    return {'ok':True,'approval':'already_approved'}
                if d.status!='pending_approval' or d.publish_state!='unpublished':
                    raise ValueError('Hanya draf pending yang belum dipublikasikan dapat disetujui.')
                if bot:bot.answer(cb_id,'Menyetujui draft yang sudah Anda periksa')
                # Do not re-run QC or auto-rewrite content after owner presses
                # Approve. The preview is the text the owner consented to.
                if not (d.image_url or d.image_local_path) and (
                        d.source_image_url or d.source_image_path):
                    render_draft(d)
                approve(db,d,uid)
                if CONFIG.photo_music_mode == 'off':
                    # Approval records consent but NEVER posts. The owner may
                    # separately choose Post Sekarang or wait for schedule.
                    db.add(Audit(draft_id=d.id,event='photo_only_approved',
                                 actor=str(uid),detail={'version':d.version}))
                    d.rights_reviewed=True
                    db.add(Audit(draft_id=d.id,event='photo_reviewed_by_owner',
                                 actor=str(uid),detail={'version':d.version,
                                                        'source':'telegram_final_approve'}))
                schedule_approved(db,daily_limit=CONFIG.daily_limit)
                db.commit()
                at=d.scheduled_at.astimezone(WIB).strftime('%d %b %Y %H:%M WIB') if d.scheduled_at else 'belum tersedia'
                if bot:
                    bot.message(chat_id,'✅ Draft versi '+str(d.version)+' disetujui dan dijadwalkan: '+at,
                                with_home_button({'inline_keyboard':[[
                                    {'text':'📸 Post Sekarang',
                                     'callback_data':f'postnow:{d.id}:{d.version}'}]]}))
                if CONFIG.photo_music_mode=='manual':
                    from .stock_flow import send_music_kit
                    try:
                        send_music_kit(db,d,st,bot,chat_id)
                        send('📦 Cover dan caption sudah dikirim. Simpan sebagai Draft Instagram '
                             'dan tambahkan musik. Bot mengingatkan saat jadwal posting.')
                    except (ValueError,RuntimeError,OSError,httpx.HTTPError) as kit_error:
                        db.rollback()
                        send('⚠️ Approval dan jadwal tetap tersimpan, tetapi paket Draft Instagram '
                             'belum terkirim: '+type(kit_error).__name__+
                             '. Bot akan mencoba kembali saat pemeriksaan berkala.')

            elif action=='reject':
                if d.status=='published' or d.publish_state in {'publishing','published','uncertain','awaiting_container'}:
                    raise ValueError('Posting sudah terbit atau sedang diproses, tidak dapat ditolak.')
                d.status='rejected';d.scheduled_at=None
                db.add(Audit(draft_id=d.id,event='rejected',actor=str(uid)))
                db.commit()
                from .automation_mode import current_mode, MANUAL_POST
                if current_mode(db)[0]==MANUAL_POST:
                    from .replacements import offer_replacements
                    try:
                        choices=offer_replacements(db,d,uid,bot,chat_id)
                    except (ValueError,RuntimeError,httpx.HTTPError,OSError):
                        db.rollback()
                        send('❌ Berita ditolak. Gagal menampilkan pilihan pengganti. '
                             'Buka kembali daftar kandidat berita.',finished=True)
                    return {'ok':True,'rejected':d.id}
                send('❌ Draf ditolak. Tidak akan dipublikasikan.',finished=True)
            elif action=='sources':
                lines=[f'Sumber utama: {st.source_url}',f'Verifikasi: {st.verification_status}',
                       f'Foto: {d.media_page_url}',f'Kredit: {d.image_credit}',f'Lisensi: {d.photo_license}',
                       f'URL lisensi: {d.image_license_url}']
                for e in (st.evidence or [])[:8]:lines.append(f'Klaim: {e.get("claim")}\nKutipan sumber: {e.get("quote","(manual import)")}\n{e.get("url")}')
                send('\n\n'.join(lines)[:4000])
            elif action=='credit':
                if not (d.source_image_url or d.image_url):
                    raise ValueError('Pilih foto sebelum mengisi kredit dan lisensi.')
                sess=db.get(TelegramSession,str(uid))
                if sess:db.delete(sess);db.flush()
                db.add(TelegramSession(user_id=str(uid),draft_id=d.id,mode='photo_credit',version=d.version))
                db.commit()
                send('🧾 Periksa artikel sumber dan lisensi foto. Balas dengan:\\n'
                     'Kredit: Nama pemilik/kreator\\nLisensi: Nama lisensi/hak penggunaan\\n'
                     'Sumber: https://...\\n\\n'
                     'Jangan menganggap foto NASA/ESA otomatis bebas hak cipta. '
                     'Kredit dan lisensi ini opsional di Telegram; cek hak penggunaan sebelum posting.')
            elif action=='rights':
                # Legacy inline buttons may remain in old Telegram messages.
                send('ℹ️ Verifikasi foto terpisah sudah tidak diperlukan. '
                     'Periksa cover dan sumber, lalu langsung klik Approve.')
            elif action in ('highlight','caption','photo','manualhook','green'):
                if d.status in ('published','rejected') or d.publish_state in ('publishing','published','uncertain'):
                    raise ValueError('Draf ini tidak dapat diedit.')
                sess=db.get(TelegramSession,str(uid))
                if sess:db.delete(sess);db.flush()
                mode='manual_hook' if action=='manualhook' else action
                db.add(TelegramSession(user_id=str(uid),draft_id=d.id,mode=mode,version=d.version))
                db.commit()
                if action=='manualhook':
                    send('✍️ Kirim satu headline baru dalam pesan Telegram berikutnya. '
                         'Teks Anda akan dipakai PERSIS, tanpa ditulis ulang AI. '
                         'Sistem memeriksa angka sumber, format, dan keterbacaan cover. '
                         'Setelah tersimpan, gunakan 📋 Hasil QC. /cancel untuk batal.')
                elif action=='highlight':
                    send('✏️ Kirim instruksi agar AI merevisi hook, misalnya "Buat lebih personal". '
                         'Untuk menulis sendiri tanpa AI, gunakan Tulis Hook Sendiri. /cancel untuk batal.')
                elif action=='caption':
                    send('📝 Kirim instruksi atau teks pengganti caption. /cancel untuk batal.')
                elif action=='green':
                    send('🟢 Kirim kata/frasa yang ingin berwarna hijau PERSIS dari headline, '
                         'pisahkan dengan koma. Contoh: LUBANG HITAM, GALAKSI. '
                         'Headline tidak diubah. /cancel untuk batal.')
                else:
                    send('🖼 Kirim foto langsung, URL HTTPS, atau kata kunci Commons. '
                         'Foto memerlukan kredit dan pemeriksaan hak penggunaan. /cancel untuk batal.')
            elif action.startswith('pick') and action[4:].isdigit():
                idx=int(action[4:]);opts=d.photo_candidates or []
                if idx>=len(opts):raise ValueError('Pilihan foto tidak valid.')
                opt=opts[idx]
                _replace_photo(db,d,opt['image_url'],uid,details=opt)
                editing=db.get(TelegramSession,str(uid))
                if editing:db.delete(editing)
                db.commit();send_preview(bot,chat_id,d,st) if bot else None
                send('Foto diganti. Tinjau lisensi sebelum Approve; approval lama sudah batal.')
            else:raise ValueError('Pilihan tidak dikenali.')
            if bot and action not in ('hookideas','retrycover','autofit','qc','approve'):bot.answer(cb_id,'Diterima')
        except (ValueError,RuntimeError,httpx.HTTPError,OSError) as exc:
            db.rollback()
            if bot:bot.answer(cb_id,'Permintaan perlu diperbaiki')
            send('⚠️ '+str(exc)[:300])
        return {'ok':True}
    if msg:
        txt=(msg.get('text') or msg.get('caption') or '').strip()
        sess=db.get(TelegramSession,str(uid))
        if txt in ('/testnews','/testgemini','/testcover') and not sess:
            send('ℹ️ Perintah percobaan lama sudah dinonaktifkan. Gunakan menu AutoNews terbaru.',True)
            return {'ok':True,'deprecated_command':txt[1:]}
        if txt=='/generate' and not sess:
            send('📰 Menyiapkan satu berita untuk approval…')
            send(generate_news_now(db,bot,chat_id))
            return {'ok':True,'command':'generate'}
        if txt in ('/start','/help') and not sess:
            send('🛰 Unfounded Theory Newsroom\n\nPilih tombol di bawah untuk mengelola berita.',True)
            return {'ok':True,'command':'help'}
        if txt in ('/queue','/pending','/approved','/stories','/status') and not sess:
            from sqlalchemy import func
            if txt=='/status':
                groups=db.execute(select(Draft.status,func.count(Draft.id)).group_by(Draft.status)).all()
                send('📊 Status redaksi\n'+('\n'.join(f'{status}: {qty}' for status,qty in groups) or 'Belum ada berita')+'\n\n'+automation_status(db))
            elif txt=='/pending':
                show_pending()
            elif txt=='/approved':
                show_approved()
            elif txt=='/stories':
                show_stories()
            else:
                rows=db.execute(select(Draft).where(Draft.status=='approved',Draft.scheduled_at.is_not(None)).order_by(Draft.scheduled_at).limit(15)).scalars().all()
                def row(d):
                    at=d.scheduled_at.replace(tzinfo=timezone.utc) if d.scheduled_at.tzinfo is None else d.scheduled_at
                    return f'{at.astimezone(WIB):%d/%m %H:%M} - {d.highlight}'
                send('📆 Jadwal WIB\n'+('\n'.join(row(d) for d in rows) or 'Belum ada antrean'))
            return {'ok':True,'command':txt[1:]}
        if txt=='/cancel' and sess:
            db.delete(sess);db.commit();send('Revisi dibatalkan.',finished=True)
        elif sess and (txt or (sess.mode=='photo' and msg.get('photo'))):
            d=db.get(Draft,sess.draft_id)
            if not d or d.version!=sess.version:
                db.delete(sess);db.commit();send('Sesi revisi kedaluwarsa, buka draf terbaru.')
            else:
                st=db.get(Story,d.story_id)
                try:
                    if sess.mode=='photo' and msg.get('photo'):
                        if not bot:raise ValueError('Bot Telegram belum dikonfigurasi')
                        best=max(msg['photo'],key=lambda x:x.get('width',0)*x.get('height',0))
                        _replace_telegram_photo(db,d,best['file_id'],uid,bot)
                        sess.mode='photo_credit'
                        sess.version=d.version
                        db.commit()
                        send_editor_preview(db,bot,chat_id,d,st)
                        send('Foto diterima. Balas dua baris seperti ini:\nKredit: NASA/Chandra\nLisensi: Public domain\nTambahkan URL sumber jika ada. /cancel untuk batal.')
                        return {'ok':True,'awaiting':'photo_credit'}
                    if sess.mode=='manual_post_link':
                        from .automation_mode import manual_post_ready
                        if not manual_post_ready(db,d) or d.publish_state!='unpublished':
                            raise ValueError('Konfirmasi manual tidak berlaku untuk berita ini.')
                        link=instagram_post_url(txt)
                        d.status='published';d.publish_state='published';d.scheduled_at=None
                        db.add(Audit(draft_id=d.id,event='manual_post_confirmed',actor=str(uid),
                                     detail={'version':d.version,'post_url':link}))
                        db.delete(sess);db.commit()
                        send('✅ Post manual dicatat: '+link+' (tanpa posting API oleh bot).')
                        return {'ok':True,'manual_post':'confirmed'}
                    if sess.mode=='music_post_link':
                        from .stock_flow import music_kit_sent, is_auto_approved
                        if (d.status!='approved' or is_auto_approved(db,d) or
                            not (d.publish_state=='manual_music_pending' or
                                 (d.publish_state=='unpublished' and music_kit_sent(db,d)))):
                            raise ValueError('Handoff musik tidak lagi menunggu konfirmasi.')
                        link=instagram_post_url(txt)
                        d.status='published'
                        d.publish_state='published'
                        db.add(Audit(draft_id=d.id,event='ig_music_manual_confirmed',
                                     actor=str(uid),detail={'version':d.version,
                                        'post_url':link,
                                        'note':'Confirmed by human editor, not independently API verified'}))
                        db.delete(sess)
                        db.commit()
                        fb=publish_facebook_once(db,d,actor=str(uid))
                        send('✅ Post Instagram dicatat sesuai konfirmasi Anda.\\n'
                             'URL: '+link+'\\nFacebook: '+str(fb.get('facebook'))+
                             '\\nTidak ada publikasi foto tanpa musik oleh bot.')
                        return {'ok':True,'instagram':'editor_confirmed',
                                'facebook':fb.get('facebook')}
                    if sess.mode=='photo_credit':
                        # Deliberately requires manual attribution information from owner.
                        import re
                        c=re.search(r'(?im)^kredit\s*:\s*(.+)$',txt)
                        lic=re.search(r'(?im)^lisensi\s*:\s*(.+)$',txt)
                        link=re.search(r'(?im)^sumber\s*:\s*(https://\S+)',txt)
                        if not c or not lic or len(c.group(1).strip())<3 or len(lic.group(1).strip())<2:
                            raise ValueError('Kirim Kredit: ... dan Lisensi: ... pada dua baris terpisah.')
                        d.image_credit=c.group(1).strip()[:250]
                        d.photo_license=lic.group(1).strip()[:120]
                        if link:d.media_page_url=link.group(1)
                        # Review button still required, never self-certify permission.
                    elif sess.mode=='green':
                        if not (d.source_image_url or d.source_image_path):
                            raise ValueError('Foto sumber asli diperlukan untuk merender ulang highlight hijau.')
                        from .accent import manual_green_phrases
                        chosen=manual_green_phrases(d.highlight,txt)
                        revise(db,d,'highlight',d.highlight,uid)
                        d.accent_words=chosen
                        if d.source_image_url or d.source_image_path:
                            render_draft(d)
                        db.add(Audit(draft_id=d.id,event='green_highlight_changed',
                                     actor=str(uid),detail={'version':d.version,
                                                            'phrases':chosen[1:]}))
                    elif sess.mode in ('highlight','caption','manual_hook'):
                        if sess.mode=='manual_hook':
                            from .manual_hook import validate_typed_hook,accent_for_hook
                            value=validate_typed_hook(txt,st,CONFIG.font_path)
                            if value==d.highlight:
                                raise ValueError('Hook sama dengan yang sekarang. Tulis versi baru atau /cancel.')
                            revise(db,d,'highlight',value,uid)
                            d.accent_words=accent_for_hook(value,d.accent_words)
                            db.add(Audit(draft_id=d.id,event='manual_hook_submitted',
                                         actor=str(uid),detail={'version':d.version,
                                          'source':'telegram_direct_text',
                                          'editorial_qc_required':True}))
                            if d.source_image_url or d.source_image_path:
                                try:
                                    render_draft(d)
                                except (ValueError,RuntimeError,httpx.HTTPError,OSError) as exc:
                                    d.image_url=None
                                    d.image_local_path=None
                                    d.last_error='Render cover: '+str(exc)[:220]
                            else:
                                d.last_error='Foto sumber belum tersedia. Gunakan Ganti Foto.'
                        else:
                            value=_revision_text(sess.mode,txt,d,st)
                            if sess.mode=='highlight':
                                from .renderer import require_cover_fit
                                require_cover_fit(value,CONFIG.font_path)
                            revise(db,d,sess.mode,value,uid)
                            if sess.mode=='highlight' and (d.source_image_url or d.source_image_path):
                                render_draft(d)
                    elif sess.mode=='photo':
                        if txt.startswith('https://'):
                            _replace_photo(db,d,txt,uid)
                        else:
                            opts=find_photos(txt,limit=3)
                            if not opts:raise ValueError('Tidak ada foto dengan metadata lisensi yang memenuhi syarat.')
                            d.photo_candidates=opts;db.commit()
                            send('Pilihan foto Commons ditemukan. Tinjau tautan dan lisensi sebelum memilih:\n'+
                                 '\n'.join(f'{i+1}. {opt["title"]}: {opt["page_url"]}' for i,opt in enumerate(opts)))
                            if bot:bot.message(chat_id,'Pilih foto:',photo_keyboard(d))
                            return {'ok':True,'photo_options':len(opts)}
                    manual=(sess.mode=='manual_hook')
                    db.delete(sess);db.commit()
                    send_editor_preview(db,bot,chat_id,d,st)
                    if manual:
                        send('✅ Hook tulisan Anda tersimpan tanpa perubahan oleh AI. '
                             'Approval dan QC versi lama dibatalkan. '
                             'Tekan 📋 Hasil QC untuk memeriksa curiosity gap serta akurasi. '+
                             ('Cover terbaru siap diperiksa.' if d.image_url or d.image_local_path else
                              'Cover belum tersedia: '+str(d.last_error or 'Pilih foto sumber.')))
                    else:
                        send('✏️ Versi baru tersimpan. Approval versi sebelumnya dibatalkan.',finished=True)
                except (ValueError,RuntimeError,httpx.HTTPError,OSError) as exc:
                    db.rollback();send('⚠️ '+str(exc)[:300]+' Coba ulangi atau /cancel.')
    return {'ok':True}

@app.post('/jobs/reschedule',dependencies=[Depends(worker_auth)])
def reschedule_job(db=Depends(session)):
    scheduled=schedule_approved(db,daily_limit=CONFIG.daily_limit)
    db.commit()
    return {'scheduled':[{'draft_id':i,'at':t.isoformat() if t else None} for i,t in scheduled]}

def _manual_photo_music_handoff(db):
    """Approved due photo: send editor a native-music posting kit, never a mute JPEG."""
    if not CONFIG.telegram_token or not CONFIG.chat_id:
        return {'manual_music':'blocked','reason':'Telegram credentials missing'}
    now=datetime.now(timezone.utc)
    from .stock_flow import is_auto_approved, send_music_kit, music_kit_sent
    q=select(Draft).where(
        Draft.status=='approved',Draft.approved_version==Draft.version,
        Draft.publish_state=='unpublished',
        Draft.scheduled_at.is_not(None),Draft.scheduled_at<=now
    ).order_by(Draft.scheduled_at).limit(30)
    if db.bind.dialect.name=='postgresql':
        q=q.with_for_update(skip_locked=True)
    candidates=db.execute(q).scalars().all()
    d=next((row for row in candidates if not is_auto_approved(db,row)), None)
    if not d:return {'manual_music':'none_due'}
    # Native music requires a human Instagram posting step, not another
    # separate Telegram photo-rights click.
    if not (d.image_url or d.image_local_path):
        return {'manual_music':'blocked','reason':'Final cover missing'}
    try:
        if not d.image_url and d.image_local_path:
            d.image_url=upload_public_jpeg(d.image_local_path,f'{d.id}/v{d.version}.jpg')
        bot=TelegramClient(CONFIG.telegram_token)
        if not music_kit_sent(db,d):
            send_music_kit(db,d,db.get(Story,d.story_id),bot,CONFIG.chat_id)
        bot.message(CONFIG.chat_id,'⏰ PENGINGAT JADWAL POSTING\n\n'
                    'Buka Drafts Instagram, pilih foto + musik yang sudah disimpan, '
                    'publikasikan secara manual, lalu konfirmasi URL posting ke bot.',{
            'inline_keyboard':[[{
                'text':'🎵 Konfirmasi Post Instagram',
                'callback_data':f'musicdone:{d.id}:{d.version}'
            }]]
        })
        d.publish_state='manual_music_pending'
        db.add(Audit(draft_id=d.id,event='manual_music_handoff',
                     actor='cron',detail={'version':d.version,
                                         'scheduled_at':str(d.scheduled_at),
                                         'native_music_required':True}))
        db.commit()
        return {'manual_music':'awaiting_editor','draft_id':d.id}
    except (ValueError,RuntimeError,OSError,httpx.HTTPError) as exc:
        db.rollback()
        return {'manual_music':'handoff_error','draft_id':d.id,
                'error_type':type(exc).__name__}



def format_editorial_qc(draft, report):
    """Readable plain-text Telegram report; preserve all original QC findings."""
    gap=(report.get('checks') or {}).get('curiosity_gap') or {}
    passed=bool(report.get('passed'))
    status='✅ LOLOS' if passed else '⚠️ PERLU REVISI'
    issues=report.get('issues') or []
    manual=report.get('manual_checks') or []
    lines=[
        '📋 EDITORIAL QC',
        'Draf '+draft.id[:8]+' · Versi '+str(draft.version),
        '',
        'STATUS: '+status,
        '',
        '🔎 TEMUAN QC',
    ]
    lines.extend('• '+str(item).replace('_',' ') for item in issues) if issues else lines.append('✅ Tidak ada masalah otomatis')
    lines.extend([
        '',
        '✨ CURIOSITY GAP',
        '✅ Lolos' if gap.get('passed') else '❌ Belum lolos',
        '',
        'Pertanyaan yang harus tetap menarik:',
        str(gap.get('unanswered_question') or 'Belum teridentifikasi')[:450],
        '',
        'Alasan penilaian:',
        str(gap.get('reason') or report.get('note') or 'Tidak ada keterangan')[:800],
    ])
    if manual:
        lines.extend(['','🧾 PERIKSA MANUAL'])
        lines.extend('• '+str(item).replace('_',' ') for item in manual)
    lines.extend(['','➡️ LANGKAH BERIKUTNYA',
       'Revisi bagian yang gagal, tekan 📋 Hasil QC, lalu ✅ Approve.'
       if not passed else 'QC lulus. Anda dapat menekan ✅ Approve.'])
    return '\n'.join(lines)[:3900]


@app.post('/jobs/publish',dependencies=[Depends(worker_auth)])
def publish_job(db=Depends(session), target_draft_id=None):
    from .automation_mode import current_mode, MANUAL_POST
    from .planner_scheduling import explicitly_auto_photo
    # An explicitly scheduled, version-consented photo-only website post can
    # use Graph API even when other Telegram drafts require native music.
    # Nothing is automatically converted from the old music-required queue.
    candidate_query=select(Draft).where(
        Draft.status=='approved',Draft.approved_version==Draft.version,
        Draft.publish_state.in_(['unpublished','awaiting_container']),
        Draft.scheduled_at.is_not(None),
        Draft.scheduled_at<=datetime.now(timezone.utc)
    ).order_by(Draft.scheduled_at).limit(30)
    if target_draft_id:candidate_query=candidate_query.where(Draft.id==target_draft_id)
    explicit_due=next((d for d in db.execute(candidate_query).scalars().all()
                       if explicitly_auto_photo(db,d)),None)
    mode=current_mode(db)[0]
    if mode==MANUAL_POST and explicit_due is None:
        return {'manual_post':'owner_only','note':'Only owner-scheduled web posts may publish automatically'}
    manual_mode=CONFIG.photo_music_mode=='manual' and explicit_due is None
    if manual_mode:
        reminder=_manual_photo_music_handoff(db)
        if reminder.get('manual_music')!='none_due':
            return reminder
    elif CONFIG.photo_music_mode not in ('off','manual'):
        return {'blocked':'Invalid PHOTO_MUSIC_MODE'}
    if not CONFIG.live_publish:
        if manual_mode:return {'manual_music':'none_due', 'live_publish':False}
        return {'live_publish':False,'due_count':len(due(db)),
                'note':'DRY RUN: tidak ada permintaan dikirim ke Instagram'}
    if not CONFIG.brand_logo or not Path(CONFIG.brand_logo).is_file():
        raise HTTPException(503,'Logo resmi belum dikonfigurasi; tidak boleh live memakai placeholder')
    from .instagram_credentials import resolve_instagram_credentials
    try:
        ig_user_id,ig_token=resolve_instagram_credentials(db, CONFIG)
    except ValueError:
        raise HTTPException(503,'Instagram credential connection is not ready') from None
    # Single-worker deployment is mandatory with SQLite; Postgres supports skip_locked.
    q=select(Draft).where(Draft.status=='approved',Draft.approved_version==Draft.version,
          Draft.publish_state.in_(['unpublished','awaiting_container']),
          Draft.scheduled_at <= datetime.now(timezone.utc)).order_by(Draft.scheduled_at).limit(30)
    if target_draft_id:
        q=q.where(Draft.id == target_draft_id)
    if db.bind.dialect.name=='postgresql':q=q.with_for_update(skip_locked=True)
    rows=db.execute(q).scalars().all()
    if not manual_mode:
        # Only explicit new photo-only approvals are eligible for automatic posting.
        # Old manual-with-music approvals must never silently switch publication mode.
        consented = []
        for item in rows:
            details=db.execute(select(Audit.detail).where(
                Audit.draft_id==item.id, Audit.event=='photo_only_approved'
            )).scalars().all()
            if any((detail or {}).get('version')==item.version for detail in details):
                consented.append(item)
        rows=consented
    if manual_mode:
        from .stock_flow import is_auto_approved
        d=next((row for row in rows if is_auto_approved(db,row)),None)
    else:
        d=explicit_due if explicit_due in rows else (rows[0] if rows else None)
    if not d:return {'due':0}
    if d.expires_at:
        expires=d.expires_at.replace(tzinfo=timezone.utc) if d.expires_at.tzinfo is None else d.expires_at
        if expires<=datetime.now(timezone.utc):
            d.status='expired_needs_review';d.scheduled_at=None;db.commit()
            return {'expired':d.id}
    if not d.image_url and not d.image_local_path:
        d.last_error='Gambar final belum tersedia';db.commit()
        return {'blocked':d.id,'error':d.last_error}
    if not d.rights_reviewed:
        # Older owner-approved versions may lack the legacy review flag.
        # A version-matched photo-only approval counts as the owner's review;
        # older manual-music approvals must still remain manual.
        consents=db.execute(select(Audit.detail).where(
            Audit.draft_id==d.id,Audit.event=='photo_only_approved'
        )).scalars().all()
        if any((entry or {}).get('version')==d.version for entry in consents):
            d.rights_reviewed=True
            db.add(Audit(draft_id=d.id,event='photo_approval_backfilled',
                         actor='worker',detail={'version':d.version}))
        else:
            from .stock_flow import photo_auto_safe, is_auto_approved
            if not (manual_mode and is_auto_approved(db,d) and photo_auto_safe(d)):
                return {'blocked':d.id,'error':'Hak foto belum dikonfirmasi'}
    # Lock claim before ANY external request. Stuck publishing requires manual reconciliation.
    d.publish_state='publishing';db.commit()
    bot=_bot()
    def alert(msg):
        if bot and CONFIG.chat_id:
            try:bot.message(CONFIG.chat_id,msg)
            except Exception:log.exception('Telegram publication alert failed')
    publisher=InstagramPublisher(CONFIG.ig_base,CONFIG.ig_version,ig_user_id,ig_token)
    try:
        if not d.image_url:
            d.image_url=upload_public_jpeg(d.image_local_path,f'{d.id}/v{d.version}.jpg')
            db.commit()
        if not d.ig_container_id:
            d.ig_container_id=publisher.create_container(d.image_url,caption_text(d,allow_missing_credit=True))
            db.commit()
        status=publisher.container_status(d.ig_container_id)
        if status not in ('FINISHED','ERROR','EXPIRED'):
            d.publish_state='awaiting_container';db.commit()
            return {'waiting':d.id,'container_status':status}
        if status!='FINISHED':
            d.publish_state='uncertain';d.last_error='Media container '+str(status);db.commit()
            alert('⚠️ Instagram container error '+d.id[:8]+': '+str(status))
            return {'error':d.id,'status':status}
        # Sending media_publish is irreversible. An ambiguous timeout -> uncertain, not a retry.
        media_id=publisher.publish(d.ig_container_id)
        d.ig_media_id=media_id;d.publish_state='published';d.status='published'
        db.add(Audit(draft_id=d.id,event='published',actor='worker',detail={'instagram_media_id':media_id}))
        db.commit()
    except Exception as exc:
        db.rollback()
        d=db.get(Draft,d.id);d.publish_state='uncertain';d.last_error=str(exc)[:700];db.commit()
        alert('⚠️ Publikasi belum dapat dikonfirmasi. Jangan retry manual sebelum memeriksa Instagram. Draf '+d.id[:8])
        return {'status':'uncertain','draft_id':d.id,'note':'Reconcile on Instagram before retry'}

    # Instagram is durably confirmed before the independent Facebook action.
    # A Facebook error must never turn a successful IG post into an uncertain
    # one or cause media_publish to be repeated.
    try:
        fb=publish_facebook_once(db,d,actor='worker',config=CONFIG)
    except Exception:
        db.rollback()
        log.exception('Facebook delivery failed after confirmed Instagram publication')
        fb={'facebook':'error','requires_reconciliation':True}
    fb_status=str(fb.get('facebook','error'))
    alert('✅ Instagram berhasil terbit. Media ID: '+media_id+'\nFacebook: '+fb_status)
    return {'published':[d.id],'instagram_media_id':media_id,**fb}
