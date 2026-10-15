"""Owner-only Facebook Login for Business connection flow.

No access token in URLs/logs/HTML. Tokens are Fernet-encrypted in PostgreSQL;
publishing remains disabled until a separate successful E2E test.
"""
import hmac
import hashlib
import html
import os
import secrets
import time
from urllib.parse import urlencode
import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Form, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from .models import MetaConnection, Session
from .config import CONFIG

router=APIRouter()
COOKIE='ut_meta_oauth'
TTL=600
BASE='https://unfoundedtheory.vercel.app'
SCOPES='instagram_basic,instagram_content_publish,pages_show_list,pages_read_engagement,business_management'

def _settings():
    app_id=os.getenv('META_APP_ID','')
    secret=os.getenv('META_APP_SECRET','')
    password=os.getenv('META_CONNECT_PASSWORD','')
    encryption=os.getenv('META_TOKEN_ENCRYPTION_KEY','')
    base=os.getenv('META_OAUTH_BASE_URL', BASE).rstrip('/')
    config_id=os.getenv('META_LOGIN_CONFIG_ID','')
    if not base.startswith('https://') or '/' in base.removeprefix('https://'):
        raise HTTPException(503,'OAuth public base URL invalid')
    if not all((app_id,secret,password,encryption,config_id)):
        raise HTTPException(503,'Meta OAuth setup incomplete: configure Vercel environment variables')
    if not app_id.isdigit() or not config_id.isdigit():
        raise HTTPException(503,'Meta app/configuration ID invalid')
    try:
        Fernet(encryption.encode())
    except (ValueError,TypeError):
        raise HTTPException(503,'Meta encryption key invalid') from None
    return app_id,secret,password,encryption,base,config_id

def _page(title,body):
    return HTMLResponse('<!doctype html><html lang="id"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>'+html.escape(title)+'</title><body style="margin:6rem auto;'
        'max-width:540px;padding:0 20px;font:16px system-ui;background:#111;color:#fff">'
        '<h1>'+html.escape(title)+'</h1>'+body+'</body></html>',
        headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer',
                 'Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'"})

def _signature(data, secret):
    return hmac.new(secret.encode(),data.encode(),hashlib.sha256).hexdigest()

@router.get('/meta/connect')
def connect():
    _settings()
    return _page('Hubungkan Instagram',
       '<p>Hanya pemilik AutoNews. Login Facebook menggunakan halaman resmi Meta.</p>'
       '<form method="post" action="/api/meta/connect">'
       '<label>Password admin <input name="password" type="password" required autocomplete="off"></label>'
       '<button type="submit">Connect Instagram</button></form>')

@router.post('/meta/connect')
def connect_start(password:str=Form(...)):
    app_id,secret,admin,_,base,cfg=_settings()
    if not hmac.compare_digest(password,admin):
        raise HTTPException(403,'Wrong admin password')
    nonce=secrets.token_urlsafe(24)
    expiry=str(int(time.time())+TTL)
    state=nonce+'.'+expiry
    state=state+'.'+_signature(state,secret)
    redirect_uri=base+'/api/meta/callback'
    # Facebook Login for Business uses the exact existing configuration ID.
    url='https://www.facebook.com/'+CONFIG.ig_version+'/dialog/oauth?'+urlencode({
        'client_id':app_id,'redirect_uri':redirect_uri,'state':state,
        'response_type':'code','config_id':cfg,'scope':SCOPES})
    response=RedirectResponse(url,status_code=303)
    response.set_cookie(COOKIE,state,max_age=TTL,httponly=True,secure=True,
                        samesite='lax',path='/api/meta')
    response.headers['Cache-Control']='no-store'
    return response

def _get(client,url,params):
    res=client.get(url,params=params,timeout=20,follow_redirects=False)
    res.raise_for_status()
    data=res.json()
    if not isinstance(data,dict) or 'error' in data:
        raise ValueError('Meta response invalid')
    return data

@router.get('/meta/callback')
def callback(request:Request,code:str='',state:str='',error:str=''):
    app_id,secret,_,encryption,base,_=_settings()
    provided=request.cookies.get(COOKIE,'')
    try:
        nonce,expiry,signature=state.split('.')
        data=nonce+'.'+expiry
        ok=(bool(code) and not error and hmac.compare_digest(provided,state)
            and hmac.compare_digest(_signature(data,secret),signature)
            and time.time()<=int(expiry) and int(expiry)-time.time()<=TTL)
    except (TypeError,ValueError):
        ok=False
    if not ok:
        raise HTTPException(400,'OAuth cancelled, expired, or state invalid')
    # Only the exact redirect URI registered in Meta is accepted.
    with httpx.Client() as client:
        raw=_get(client,'https://graph.facebook.com/'+CONFIG.ig_version+'/oauth/access_token',{
            'client_id':app_id,'client_secret':secret,'redirect_uri':base+'/api/meta/callback',
            'code':code})
        short=raw.get('access_token')
        if not short:raise HTTPException(502,'Meta did not return an access token')
        exchanged=_get(client,'https://graph.facebook.com/'+CONFIG.ig_version+'/oauth/access_token',{
            'grant_type':'fb_exchange_token','client_id':app_id,
            'client_secret':secret,'fb_exchange_token':short})
        user_token=exchanged.get('access_token')
        if not user_token:raise HTTPException(502,'Meta token exchange failed')
        accounts=_get(client,'https://graph.facebook.com/'+CONFIG.ig_version+'/me/accounts',{
            'fields':'id,name,access_token,instagram_business_account',
            'access_token':user_token,'limit':100}).get('data',[])
    matches=[p for p in accounts if (p.get('instagram_business_account') or {}).get('id') and p.get('access_token')]
    if not matches:
        response=_page('Belum terhubung','<p>Tidak ditemukan Facebook Page dengan akun Instagram Professional tertaut. Hubungkan Instagram ke Page dan coba lagi.</p>')
    else:
        # Never auto-select another unrelated Page when multiple are authorized.
        if len(matches)!=1:
            response=_page('Pilih Page','<p>Ada lebih dari satu Page dengan Instagram yang terhubung. '
                'Batasi Page yang diizinkan di Facebook Login lalu coba lagi.</p>')
        else:
            page=matches[0]
            with Session() as db:
                current=db.execute(select(MetaConnection).where(MetaConnection.page_id==str(page['id']))).scalar_one_or_none()
                if not current:
                    current=MetaConnection(page_id=str(page['id']))
                    db.add(current)
                current.instagram_id=str(page['instagram_business_account']['id'])
                current.page_name=str(page.get('name',''))[:200]
                current.encrypted_page_token=Fernet(encryption.encode()).encrypt(page['access_token'].encode()).decode()
                current.updated_at=__import__('datetime').datetime.now(__import__('datetime').timezone.utc)
                db.commit()
            response=_page('Instagram terhubung',
                 '<p>Facebook Page: <strong>'+html.escape(str(page.get('name','')))+'</strong></p>'
                 '<p>Akun Instagram Professional terdeteksi. Token Page disimpan terenkripsi. '
                 'Posting otomatis masih NONAKTIF sampai pengujian selesai.</p>')
    response.delete_cookie(COOKIE,path='/api/meta')
    return response

@router.get('/meta/status')
def status():
    return {'oauth_configured':all(bool(os.getenv(x)) for x in (
        'META_APP_ID','META_APP_SECRET','META_CONNECT_PASSWORD',
        'META_TOKEN_ENCRYPTION_KEY','META_LOGIN_CONFIG_ID')),
        'callback_url':os.getenv('META_OAUTH_BASE_URL',BASE).rstrip('/')+'/api/meta/callback',
        'live_publish':False if not CONFIG.live_publish else 'requires_separate_review'}
