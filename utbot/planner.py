"""Authenticated newsroom planner: read calendar, edit copy, crop focus, plan manual posts."""
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
                           'created_at':d.created_at.isoformat(),'planned_at':(audit or {}).get('planned_at'),
                           'focus':(focus or {}).get('focus',[0.5,0.43])})
        return {'drafts':output,'timezone':'Asia/Jakarta','mode':'manual_post'}


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
        if 'planned_at' in changes:
            if payload.planned_at is not None and payload.planned_at.tzinfo is None:
                raise HTTPException(422,'Waktu rencana harus menyertakan zona waktu.')
            # Manual planning never feeds the automatic Meta publishing queue.
            db.add(Audit(draft_id=d.id,event='content_plan_changed',actor='web_editor',
                         detail={'planned_at':payload.planned_at.astimezone(timezone.utc).isoformat()
                                 if payload.planned_at else None,'manual_only':True}))
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
        db.commit()
        return {'ok':True,'id':d.id,'version':d.version,'image_url':d.image_url}


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
