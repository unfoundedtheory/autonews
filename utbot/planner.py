"""Authenticated newsroom planner: accurate covers and automatic Instagram scheduling."""
from datetime import datetime, timezone
from hashlib import sha256
from hmac import compare_digest, new as hmac_new
from pathlib import Path
import os, secrets, time
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from .models import Session, Draft, Story, Audit
from .renderer import headline_font_size, MIN_EDITORIAL_FONT_PX

router=APIRouter(prefix='/planner')
COOKIE='ut_planner'
TTL=7*24*3600


def _key():
    return os.getenv('PLANNER_PASSWORD','').encode()


def _sign(value):
    return hmac_new(_key(),value.encode(),'sha256').hexdigest()


def _permit(request: Request):
    cookie=request.cookies.get(COOKIE,'')
    timestamp,_,sig=cookie.partition('.')
    if not (_key() and timestamp.isdecimal() and len(sig)==64 and
            compare_digest(_sign(timestamp),sig) and
            0 <= time.time()-int(timestamp) <= TTL):
        raise HTTPException(401,'Silakan login ke Content Planner.')


class Login(BaseModel):
    password: str


class PhotoRights(BaseModel):
    credit: str = Field(min_length=3,max_length=160)
    license_name: str = Field(min_length=2,max_length=120)
    license_url: str = Field(min_length=12,max_length=500)
    confirmed: bool = False


class Edit(BaseModel):
    highlight: str | None=None
    caption: str | None=None
    focus_x: float | None=Field(default=None,ge=0,le=1)
    focus_y: float | None=Field(default=None,ge=0,le=1)
    planned_at: datetime | None=None


@router.get('',response_class=HTMLResponse)
def page():
    return HTMLResponse((Path(__file__).parent/'planner.html').read_text(encoding='utf-8'),
                        headers={'Cache-Control':'no-store'})


@router.post('/login')
def login(value: Login):
    if not _key() or not compare_digest(sha256(value.password.encode()).digest(),sha256(_key()).digest()):
        raise HTTPException(401,'Password planner salah atau belum dikonfigurasi.')
    stamp=str(int(time.time()))
    response=JSONResponse({'ok':True})
    response.set_cookie(COOKIE,stamp+'.'+_sign(stamp),max_age=TTL,
                        httponly=True,secure=True,samesite='strict',path='/api/planner')
    return response


@router.post('/logout')
def logout():
    response=JSONResponse({'ok':True})
    response.delete_cookie(COOKIE,path='/api/planner')
    return response


@router.get('/drafts',dependencies=[Depends(_permit)])
def drafts():
    with Session() as db:
        records=db.execute(select(Draft,Story).join(Story,Draft.story_id==Story.id)
                           .order_by(Draft.created_at.desc()).limit(180)).all()
        from .planner_scheduling import pinned_planner_schedule, explicitly_auto_photo
        from .automation_mode import current_mode
        active_mode=current_mode(db)[0]
        output=[]
        for d,st in records:
            audit=db.execute(select(Audit.detail).where(Audit.draft_id==d.id,
                         Audit.event=='content_plan_changed').order_by(Audit.id.desc()).limit(1)).scalar_one_or_none()
            focus=db.execute(select(Audit.detail).where(Audit.draft_id==d.id,
                         Audit.event=='cover_focus_changed').order_by(Audit.id.desc()).limit(1)).scalar_one_or_none()
            output.append({'id':d.id,'version':d.version,'title':st.title,
                           'source_url':st.source_url,'highlight':d.highlight,'caption':d.caption,
                           'status':d.status,'publish_state':d.publish_state,
                           'image_url':d.image_url,'source_image_url':d.source_image_url,
                           'photo_credit':d.image_credit,'photo_license':d.photo_license,
                           'image_license_url':d.image_license_url,'media_page_url':d.media_page_url,
                           'rights_reviewed':d.rights_reviewed,
                           'scheduled_at':d.scheduled_at.isoformat() if d.scheduled_at else None,
                           'auto_scheduled':explicitly_auto_photo(db,d),
                           'web_managed':pinned_planner_schedule(db,d),
                           'created_at':d.created_at.isoformat(),
                           'planned_at':d.scheduled_at.isoformat() if pinned_planner_schedule(db,d) else None,
                           'focus':(focus or {}).get('focus',[0.5,0.43])})
        from .config import CONFIG
        return {'drafts':output,'timezone':'Asia/Jakarta',
                'auto_publish_enabled':CONFIG.live_publish,
                'mode':active_mode}


@router.patch('/drafts/{draft_id}',dependencies=[Depends(_permit)])
def edit(draft_id: str, payload: Edit):
    from .editorial import revise
    from .media import render_draft
    with Session() as db:
        d=db.get(Draft,draft_id)
        if not d:
            raise HTTPException(404,'Draf tidak ditemukan.')
        if d.status in ('published','rejected') or d.publish_state!='unpublished':
            raise HTTPException(409,'Draf yang sudah dipublikasikan/ditolak tidak dapat direvisi.')
        changes=payload.model_fields_set
        if 'planned_at' in changes and ({'highlight','caption','focus_x','focus_y'} & changes):
            raise HTTPException(422,'Simpan revisi, jalankan QC, kemudian pilih jadwal otomatis.')
        if 'highlight' in changes:
            if not payload.highlight or len(payload.highlight)>245:
                raise HTTPException(422,'Headline harus berisi maksimal 245 karakter.')
            from .renderer import require_cover_fit
            try:require_cover_fit(payload.highlight)
            except ValueError as exc:raise HTTPException(422,str(exc)) from exc
            revise(db,d,'highlight',payload.highlight,'web_editor')
        if 'caption' in changes:
            if not payload.caption or len(payload.caption)>2100:
                raise HTTPException(422,'Caption tidak valid.')
            revise(db,d,'caption',payload.caption,'web_editor')
        if ('focus_x' in changes) != ('focus_y' in changes):
            raise HTTPException(422,'Kedua koordinat fokus diperlukan.')
        if 'focus_x' in changes:
            # Advance version before uploading immutable vN.jpg to storage.
            if 'highlight' not in changes and 'caption' not in changes:
                revise(db,d,'highlight',d.highlight,'web_editor')
            db.add(Audit(draft_id=d.id,event='cover_focus_changed',actor='web_editor',
                         detail={'focus':[payload.focus_x,payload.focus_y],'version':d.version}))
            db.flush()
        if {'focus_x','highlight'} & changes and (d.source_image_url or d.source_image_path):
            try:render_draft(d)
            except (ValueError,OSError,RuntimeError) as exc:
                db.rollback()
                raise HTTPException(422,'Cover gagal dirender: '+str(exc)[:160]) from exc
        if 'planned_at' in changes:
            from .planner_scheduling import schedule_web_post,unschedule_web_post
            try:
                if payload.planned_at is not None:
                    schedule_web_post(db,d,payload.planned_at)
                else:
                    unschedule_web_post(db,d)
            except ValueError as exc:
                db.rollback()
                raise HTTPException(422,str(exc)) from exc
        db.commit()
        return {'ok':True,'id':d.id,'version':d.version,'image_url':d.image_url,
                'scheduled_at':d.scheduled_at.isoformat() if d.scheduled_at else None}


@router.get('/layout/{draft_id}',dependencies=[Depends(_permit)])
def layout(draft_id: str):
    with Session() as db:
        d=db.get(Draft,draft_id)
        if not d:raise HTTPException(404,'Tidak ditemukan.')
        try:font_size=headline_font_size(d.highlight)
        except ValueError:return {'fits':False,'action':'shorten_headline'}
        return {'fits':True,'font_size':font_size,'small_font':font_size<MIN_EDITORIAL_FONT_PX,
                'suggestion':'Persingkat headline untuk tipografi yang lebih besar.'
                if font_size<MIN_EDITORIAL_FONT_PX else None}


@router.post('/drafts/{draft_id}/qc',dependencies=[Depends(_permit)])
def check_draft_qc(draft_id: str):
    """Owner-triggered editorial QC; no publication or approval side effects."""
    from .quality_control import run_draft_qc
    with Session() as db:
        draft=db.get(Draft,draft_id)
        if not draft:
            raise HTTPException(404,'Draft tidak ditemukan')
        story=db.get(Story,draft.story_id)
        report=run_draft_qc(db,draft,story,trigger='web_content_planner')
        db.commit()
        return {'passed':report.get('passed'),'issues':report.get('issues',[]),
                'version':draft.version,'status':report.get('status')}

@router.post('/drafts/{draft_id}/render',dependencies=[Depends(_permit)])
def rerender_final_cover(draft_id: str):
    """Regenerate genuine League Spartan cover with true badge and accents."""
    from .editorial import revise
    from .media import render_draft
    with Session() as db:
        d=db.get(Draft,draft_id)
        if not d or d.status in ('published','rejected') or d.publish_state!='unpublished':
            raise HTTPException(409,'Cover tidak dapat diubah pada status berita ini.')
        if not (d.source_image_url or d.source_image_path):
            raise HTTPException(422,'Sumber foto asli belum tersedia.')
        try:
            revise(db,d,'highlight',d.highlight,'web_content_studio')
            render_draft(d)
            db.commit()
        except (ValueError,OSError,RuntimeError) as exc:
            db.rollback()
            raise HTTPException(422,'Render cover gagal: '+str(exc)[:160]) from exc
        return {'ok':True,'image_url':d.image_url,'version':d.version}

@router.post('/drafts/{draft_id}/rights',dependencies=[Depends(_permit)])
def confirm_image_rights(draft_id: str, payload: PhotoRights):
    """Explicit owner's photo-rights confirmation; never inferred from NASA/ESA."""
    from urllib.parse import urlparse
    from .instagram import photo_credit_line
    with Session() as db:
        d=db.get(Draft,draft_id)
        if not d or d.status in ('published','rejected') or d.publish_state!='unpublished':
            raise HTTPException(409,'Status berita tidak mengizinkan perubahan hak foto.')
        if d.scheduled_at and d.status=='approved':
            raise HTTPException(409,'Batalkan jadwal sebelum mengganti metadata hak foto.')
        if not payload.confirmed:
            raise HTTPException(422,'Konfirmasi pemeriksaan lisensi foto diperlukan.')
        link=urlparse(payload.license_url)
        if link.scheme!='https' or not link.hostname or link.username or link.password:
            raise HTTPException(422,'URL bukti lisensi harus HTTPS yang valid.')
        if not (d.source_image_url or d.source_image_path):
            raise HTTPException(422,'Foto sumber belum tersedia.')
        old=(d.image_credit,d.photo_license,d.image_license_url,d.rights_reviewed)
        d.image_credit=payload.credit.strip()
        d.photo_license=payload.license_name.strip()
        d.image_license_url=payload.license_url.strip()
        d.rights_reviewed=True
        try:photo_credit_line(d)
        except ValueError as exc:
            db.rollback()
            raise HTTPException(422,str(exc)) from exc
        db.add(Audit(draft_id=d.id,event='photo_rights_owner_confirmed',
                     actor='web_content_studio',
                     detail={'version':d.version,'evidence_url':d.image_license_url,
                             'license_name':d.photo_license,
                             'previous_rights_reviewed':old[3]}))
        db.commit()
        return {'ok':True,'rights_reviewed':True}
