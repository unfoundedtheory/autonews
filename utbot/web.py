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
from .telegram import TelegramClient,keyboard,send_preview,photo_keyboard,main_menu
from .research import discover,fingerprint
from .rewrite import rewrite
from .pipeline import prepare_batch
from .media import find_photos,intake_image,render_draft,upload_public_jpeg

log=logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app):
    # Staging only. Real deployment uses schema migrations for production changes.
    # Never initialize disposable SQLite storage in a serverless environment.
    if not (__import__('os').environ.get('VERCEL') and CONFIG.database_url.startswith('sqlite')):
        init_db()
    yield

app=FastAPI(title='Unfounded Theory Automation',version='0.7.0',lifespan=lifespan)

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
    return {'discovery':do_discover()}

@app.get('/cron/prepare', dependencies=[Depends(cron_auth)])
def cron_prepare():
    """Prepare a small editorial batch at approximately 03:00 WIB."""
    from .runner import do_prepare
    return {'prepared':do_prepare()}

@app.get('/cron/tick/{slot}', dependencies=[Depends(cron_auth)])
def cron_tick(slot: str):
    """Publish only pre-approved eligible drafts around 06/12/18 WIB."""
    if slot not in ('morning','noon','evening'):
        raise HTTPException(404,'Invalid slot')
    from .runner import do_reschedule, do_publish
    # Publish overdue-approved items before rebuilding future slots; Hobby cron
    # can arrive up to 59 minutes after a slot begins.
    publication=do_publish()
    scheduled=do_reschedule()
    return {'queued':len(scheduled),'publication':publication}

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
        'worker_secret':bool(CONFIG.worker_secret),
        'four_line_renderer':True,
    }
    blockers=[key for key,ok in checks.items() if not ok]
    return {'ready_for_live':len(blockers)==0 and CONFIG.live_publish,
            'live_publish_enabled':CONFIG.live_publish,
            'checks':checks,'configured_ai':configured_ai,'blockers':blockers,
            'note':'This checks configuration presence, not valid external API permissions or end-to-end publishing.'}

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

def generate_test_news(db, bot, chat_id):
    """One admin request produces at most one verified editorial draft, never publishes."""
    from .research import discover, SOURCES
    import os
    if os.getenv('ENABLE_LIVE_PUBLISH', 'false').lower() != 'false':
        return '⚠️ Tes dibatalkan: ENABLE_LIVE_PUBLISH harus false.'

    def notify(d):
        if bot:
            send_preview(bot, chat_id, d, db.get(Story, d.story_id))

    def prepared(rows):
        return next((r for r in rows if r.get('status')=='prepared'), None)

    # First consume a previously discovered, unreviewed primary source.
    results=prepare_batch(db,limit=1,notifier=notify)
    done=prepared(results)
    if not done:
        # One bounded discovery pass, never a loop or background polling.
        # Prefer scientific NASA/ESA feeds; the full schedule handles all sources.
        feeds=list(discover(db,sources=SOURCES[:4]))
        db.commit()
        count=sum(item.get('inserted',0) for item in feeds)
        if count:
            results=prepare_batch(db,limit=1,notifier=notify)
            done=prepared(results)
        else:
            details='; '.join(f"{item['feed']}: {str(item['error'])[:70]}"
                              for item in feeds if item.get('error'))
            return ('⚠️ Belum ada berita baru dari sumber resmi. '
                    'Discovery langsung sudah dijalankan (NASA/APOD/ESA). '
                    + ('Kendala feed: '+details[:350] if details else
                       'Berita pada feed mungkin sudah tersimpan atau melewati batas usia.'))

    if done:
        if done.get('notify_error'):
            return '⚠️ Draf berhasil dibuat, tetapi preview Telegram gagal: '+str(done['notify_error'])[:300]
        if done.get('has_photo'):
            return '✅ Satu draf dan cover dibuat. Preview dikirim untuk approval; tidak ada posting Instagram.'
        return ('⚠️ Satu draf dibuat, tetapi cover 4:5 belum tersedia. Diagnostik: '
                +str(done.get('photo_error') or 'Tidak ada rincian')[:420])
    if results:
        return '⚠️ Sumber dicoba tetapi gagal QC: '+str(results[0].get('reason','Unknown'))[:300]
    return '⚠️ Tidak ditemukan kandidat yang dapat diproses dari sumber resmi.'

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
            'ready_for_approval':evidence_ready(story) and story.verification_status=='verified' and d.rights_reviewed}

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
    src=Path(CONFIG.media_dir)/d.id/f'source_v{d.version+1}.jpg'
    photo_path=intake_image(url,str(src))
    revise(db,d,'source_image_url',url,uid)
    d.source_image_path=photo_path
    d.image_credit=(details or {}).get('credit') or 'Kredit foto: perlu diisi oleh editor'
    d.photo_license=(details or {}).get('license') or 'Editor-supplied; explicit rights confirmation required'
    d.image_license_url=(details or {}).get('license_url')
    d.media_page_url=(details or {}).get('page_url') or url
    d.photo_candidates=[]
    render_draft(d)

def _replace_telegram_photo(db,d,file_id,uid,bot):
    """Editor-supplied Telegram photo; license review and attribution still required."""
    from .media import render_draft
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
    def send(s,menu=False):
        if bot:bot.message(chat_id,s,main_menu() if menu else None)
    if cb and str(cb.get('data','')).startswith('nav:'):
        action=cb['data'][4:]
        if action not in ('home','pending','queue','status','test_gemini','test_news'):
            if bot:bot.answer(cb.get('id'),'Menu tidak valid')
            return {'ok':True}
        if action=='test_news':
            if bot:bot.answer(cb.get('id'),'Memproses satu draf')
            send('📰 Memproses satu berita percobaan...')
            send(generate_test_news(db,bot,chat_id))
        elif action=='test_gemini':
            send(gemini_test_message(),True)
        elif action=='home':
            send('🛰 Unfounded Theory Newsroom\\nPilih menu di bawah.',True)
        elif action=='status':
            from sqlalchemy import func
            groups=db.execute(select(Draft.status,func.count(Draft.id)).group_by(Draft.status)).all()
            send('📊 Status redaksi\\n'+('\\n'.join(f'{s}: {n}' for s,n in groups) or 'Belum ada berita'),True)
        elif action=='pending':
            rows=db.execute(select(Draft).where(Draft.status=='pending_approval').order_by(Draft.created_at.desc()).limit(10)).scalars().all()
            send('📝 Pending Approval\\n'+('\\n'.join(f'{d.id[:8]}: {d.highlight}' for d in rows) or 'Tidak ada'),True)
        else:
            rows=db.execute(select(Draft).where(Draft.status=='approved',Draft.scheduled_at.is_not(None)).order_by(Draft.scheduled_at).limit(15)).scalars().all()
            send('📅 Jadwal WIB\\n'+('\\n'.join(f'{d.scheduled_at.astimezone(WIB):%d/%m %H:%M} - {d.highlight}' for d in rows) or 'Belum ada antrean'),True)
        if bot and action!='test_news':bot.answer(cb.get('id'),'Diperbarui')
        return {'ok':True,'menu':action}
    if cb:
        cb_id=cb.get('id')
        try:
            action,ident,v=cb.get('data','').split(':',2)
            version=int(v);UUID(ident)
        except (TypeError,ValueError):
            if bot:bot.answer(cb_id,'Tombol tidak valid')
            return {'ok':True}
        d=db.get(Draft,ident)
        if not d or d.version!=version:
            if bot:bot.answer(cb_id,'Versi lama, buka draf terbaru')
            return {'ok':True,'stale':True}
        st=db.get(Story,d.story_id)
        try:
            if action=='hookideas':
                if d.status in ('published','rejected') or d.publish_state in ('publishing','published','uncertain'):
                    raise ValueError('Draf ini tidak boleh direvisi.')
                if bot:bot.answer(cb_id,'Menyusun alternatif hook')
                from .hook_editor import alternatives
                ideas=alternatives(d,st)
                db.add(Audit(draft_id=d.id,event='hook_candidates',actor=str(uid),
                             detail={'version':d.version,'options':ideas}))
                db.commit()
                rows=[[{'text':f'Pilih Hook {i+1}','callback_data':f'pickh{i}:{d.id}:{d.version}'}]
                      for i in range(len(ideas))]
                if bot:bot.message(chat_id,'✨ Alternatif hook dari sumber yang sama: '+
                    '\\n\\n'+'\\n\\n'.join(f'{i+1}. {h}' for i,h in enumerate(ideas))+
                    '\\n\\nPilih salah satu. Semua tetap perlu pemeriksaan editorial.',
                    {'inline_keyboard':rows})
            elif action.startswith('pickh') and action[5:].isdigit():
                index=int(action[5:])
                report=db.query(Audit).filter(Audit.draft_id==d.id,
                            Audit.event=='hook_candidates').order_by(Audit.id.desc()).first()
                choices=(report.detail or {}).get('options',[]) if report and (report.detail or {}).get('version')==d.version else []
                if index>=len(choices):raise ValueError('Opsi hook kedaluwarsa. Buat ulang alternatif.')
                revise(db,d,'highlight',choices[index],uid)
                d.accent_words=[]
                db.add(Audit(draft_id=d.id,event='hook_selected',actor=str(uid),
                             detail={'version':d.version,'source_version':version,'choice':index+1}))
                if d.source_image_url or d.source_image_path:
                    render_draft(d)
                db.commit()
                if bot:send_preview(bot,chat_id,d,st)
                send('✨ Hook diperbarui. QC dan approval harus diperiksa lagi.')
            elif action=='qc':
                from .quality_control import report_for_draft
                report=report_for_draft(db,d,st)
                send('📋 Editorial QC | Draf '+d.id[:8]+' v'+str(d.version)+
                     '\\nStatus: '+report.get('status','unknown')+
                     '\\nPercobaan: '+str(report.get('attempts','n/a'))+
                     '\\nMasalah: '+(', '.join(report.get('issues',[])) or 'Tidak ada')+
                     '\\nPeriksa manual: '+', '.join(report.get('manual_checks',[])))
            elif action=='approve':
                approve(db,d,uid)
                schedule_approved(db,daily_limit=CONFIG.daily_limit)
                db.commit()
                at=d.scheduled_at.astimezone(WIB).strftime('%d %b %Y %H:%M WIB') if d.scheduled_at else 'belum tersedia'
                send('✅ Disetujui untuk versi '+str(d.version)+'. Jadwal: '+at)
            elif action=='reject':
                if d.status=='published' or d.publish_state in {'publishing','published','uncertain','awaiting_container'}:
                    raise ValueError('Posting sudah terbit atau sedang diproses, tidak dapat ditolak.')
                d.status='rejected';d.scheduled_at=None
                db.add(Audit(draft_id=d.id,event='rejected',actor=str(uid)))
                db.commit();send('❌ Draf ditolak. Tidak akan dipublikasikan.')
            elif action=='sources':
                lines=[f'Sumber utama: {st.source_url}',f'Verifikasi: {st.verification_status}',
                       f'Foto: {d.media_page_url}',f'Kredit: {d.image_credit}',f'Lisensi: {d.photo_license}',
                       f'URL lisensi: {d.image_license_url}']
                for e in (st.evidence or [])[:8]:lines.append(f'Klaim: {e.get("claim")}\nKutipan sumber: {e.get("quote","(manual import)")}\n{e.get("url")}')
                send('\n\n'.join(lines)[:4000])
            elif action=='rights':
                if not (d.source_image_url or d.image_url) or not d.photo_license or not d.image_credit:
                    raise ValueError('Foto, kredit, dan lisensi harus lengkap sebelum konfirmasi.')
                d.rights_reviewed=True
                db.add(Audit(draft_id=d.id,event='photo_rights_confirmed',actor=str(uid),
                             detail={'photo':d.media_page_url,'license':d.photo_license}))
                db.commit();send('📄 Hak penggunaan foto dikonfirmasi. Anda bertanggung jawab memeriksa syarat lisensi dan kecocokan foto.')
            elif action in ('highlight','caption','photo'):
                sess=db.get(TelegramSession,str(uid))
                if sess:db.delete(sess);db.flush()
                db.add(TelegramSession(user_id=str(uid),draft_id=d.id,mode=action,version=d.version))
                db.commit()
                send('Kirim instruksi revisi atau teks pengganti. Untuk foto, kirim gambar langsung, URL HTTPS yang boleh digunakan, atau kata kunci Commons. Foto yang Anda unggah perlu kredit dan lisensi. /cancel untuk batal.')
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
            if bot and action!='hookideas':bot.answer(cb_id,'Diterima')
        except (ValueError,RuntimeError,httpx.HTTPError,OSError) as exc:
            db.rollback()
            if bot:bot.answer(cb_id,'Permintaan perlu diperbaiki')
            send('⚠️ '+str(exc)[:300])
        return {'ok':True}
    if msg:
        txt=(msg.get('text') or msg.get('caption') or '').strip()
        sess=db.get(TelegramSession,str(uid))
        if txt=='/testnews' and not sess:
            send('📰 Memproses satu berita percobaan...')
            send(generate_test_news(db,bot,chat_id))
            return {'ok':True,'command':'testnews'}
        if txt=='/testgemini' and not sess:
            send(gemini_test_message(),True)
            return {'ok':True,'command':'testgemini'}
        if txt in ('/start','/help') and not sess:
            send('🛰 Unfounded Theory Newsroom\n\nPilih tombol di bawah untuk mengelola berita.',True)
            return {'ok':True,'command':'help'}
        if txt in ('/queue','/pending','/status') and not sess:
            from sqlalchemy import func
            if txt=='/status':
                groups=db.execute(select(Draft.status,func.count(Draft.id)).group_by(Draft.status)).all()
                send('📊 Status redaksi\n'+('\n'.join(f'{status}: {qty}' for status,qty in groups) or 'Belum ada berita'))
            elif txt=='/pending':
                pending=db.execute(select(Draft).where(Draft.status=='pending_approval').order_by(Draft.created_at.desc()).limit(10)).scalars().all()
                send('📝 Menunggu approval\n'+('\n'.join(f'{d.id[:8]} v{d.version}: {d.highlight}' for d in pending) or 'Tidak ada'))
            else:
                rows=db.execute(select(Draft).where(Draft.status=='approved',Draft.scheduled_at.is_not(None)).order_by(Draft.scheduled_at).limit(15)).scalars().all()
                def row(d):
                    at=d.scheduled_at.replace(tzinfo=timezone.utc) if d.scheduled_at.tzinfo is None else d.scheduled_at
                    return f'{at.astimezone(WIB):%d/%m %H:%M} - {d.highlight}'
                send('📆 Jadwal WIB\n'+('\n'.join(row(d) for d in rows) or 'Belum ada antrean'))
            return {'ok':True,'command':txt[1:]}
        if txt=='/cancel' and sess:
            db.delete(sess);db.commit();send('Revisi dibatalkan.')
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
                        if bot:send_preview(bot,chat_id,d,st)
                        send('Foto diterima. Balas dua baris seperti ini:\nKredit: NASA/Chandra\nLisensi: Public domain\nTambahkan URL sumber jika ada. /cancel untuk batal.')
                        return {'ok':True,'awaiting':'photo_credit'}
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
                    elif sess.mode in ('highlight','caption'):
                        value=_revision_text(sess.mode,txt,d,st)
                        revise(db,d,sess.mode,value,uid)
                        if sess.mode=='highlight' and d.source_image_path:render_draft(d)
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
                    db.delete(sess);db.commit()
                    if bot:send_preview(bot,chat_id,d,st)
                    send('✏️ Versi baru tersimpan. Approval versi sebelumnya dibatalkan.')
                except (ValueError,RuntimeError,httpx.HTTPError,OSError) as exc:
                    db.rollback();send('⚠️ '+str(exc)[:300]+' Coba ulangi atau /cancel.')
    return {'ok':True}

@app.post('/jobs/reschedule',dependencies=[Depends(worker_auth)])
def reschedule_job(db=Depends(session)):
    scheduled=schedule_approved(db,daily_limit=CONFIG.daily_limit)
    db.commit()
    return {'scheduled':[{'draft_id':i,'at':t.isoformat() if t else None} for i,t in scheduled]}

@app.post('/jobs/publish',dependencies=[Depends(worker_auth)])
def publish_job(db=Depends(session)):
    if not CONFIG.live_publish:
        return {'live_publish':False,'due_count':len(due(db)),
                'note':'DRY RUN: tidak ada permintaan dikirim ke Instagram'}
    if not CONFIG.brand_logo or not Path(CONFIG.brand_logo).is_file():
        raise HTTPException(503,'Logo resmi belum dikonfigurasi; tidak boleh live memakai placeholder')
    if not all((CONFIG.ig_user_id,CONFIG.ig_token)):
        raise HTTPException(503,'Meta API not configured')
    # Single-worker deployment is mandatory with SQLite; Postgres supports skip_locked.
    q=select(Draft).where(Draft.status=='approved',Draft.approved_version==Draft.version,
          Draft.publish_state.in_(['unpublished','awaiting_container']),
          Draft.scheduled_at <= datetime.now(timezone.utc)).order_by(Draft.scheduled_at).limit(1)
    if db.bind.dialect.name=='postgresql':q=q.with_for_update(skip_locked=True)
    d=db.execute(q).scalars().first()
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
        return {'blocked':d.id,'error':'Hak foto belum dikonfirmasi'}
    # Lock claim before ANY external request. Stuck publishing requires manual reconciliation.
    d.publish_state='publishing';db.commit()
    bot=_bot()
    def alert(msg):
        if bot and CONFIG.chat_id:
            try:bot.message(CONFIG.chat_id,msg)
            except Exception:log.exception('Telegram publication alert failed')
    publisher=InstagramPublisher(CONFIG.ig_base,CONFIG.ig_version,CONFIG.ig_user_id,CONFIG.ig_token)
    try:
        if not d.image_url:
            d.image_url=upload_public_jpeg(d.image_local_path,f'{d.id}/v{d.version}.jpg')
            db.commit()
        if not d.ig_container_id:
            d.ig_container_id=publisher.create_container(d.image_url,caption_text(d))
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
        alert('✅ Unfounded Theory berhasil terbit. Media ID: '+media_id)
        return {'published':[d.id],'instagram_media_id':media_id}
    except Exception as exc:
        db.rollback()
        d=db.get(Draft,d.id);d.publish_state='uncertain';d.last_error=str(exc)[:700];db.commit()
        alert('⚠️ Publikasi belum dapat dikonfirmasi. Jangan retry manual sebelum memeriksa Instagram. Draf '+d.id[:8])
        return {'status':'uncertain','draft_id':d.id,'note':'Reconcile on Instagram before retry'}
