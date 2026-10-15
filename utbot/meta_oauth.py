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

def _page(title,body,status_code=200):
    nonce=secrets.token_urlsafe(16)
    css="""*{box-sizing:border-box}html{color-scheme:dark}body{min-height:100vh;margin:0;background:#0b0d11;color:#f2f2f5;font:16px/1.55 system-ui,sans-serif;display:grid;place-items:center;padding:24px}main{width:min(100%,460px)}.brand{font-size:13px;font-weight:800;letter-spacing:.2em;color:#ff8a48;margin:0 0 24px}.panel{padding:clamp(24px,6vw,40px);border:1px solid #343842;border-radius:20px;background:#181b22;box-shadow:0 24px 70px #0006}h1{font-size:clamp(24px,5vw,30px);line-height:1.2;letter-spacing:-.04em;margin:0 0 12px}p{color:#bec0c8;margin:0 0 24px}label{display:block;font-weight:600;font-size:14px;margin-bottom:8px}.field{display:flex;align-items:center;border:1px solid #545963;border-radius:10px;background:#101218;overflow:hidden}.field:focus-within{outline:2px solid #ff8a48}input{flex:1;min-width:0;background:transparent;border:0;padding:14px;font:inherit;color:#fff;outline:0}button{font:inherit;cursor:pointer}.reveal{background:none;border:0;color:#f1b18e;padding:12px;min-width:72px}.primary{display:block;width:100%;margin-top:18px;padding:14px;background:#d95413;color:white;border:0;border-radius:10px;font-weight:700}.primary:hover{background:#b7450b}.help{font-size:13px;margin:16px 0 0;color:#a7aab5}.alert{border:1px solid #a64d39;background:#3b2220;padding:12px;border-radius:10px;color:#ffd6c7;margin-bottom:18px}a{color:#ff9d6a}"""
    script="""const b=document.getElementById('reveal'),p=document.getElementById('password');if(b&&p){b.addEventListener('click',()=>{const show=p.type==='password';p.type=show?'text':'password';b.textContent=show?'Sembunyikan':'Lihat';b.setAttribute('aria-pressed',String(show));});}"""
    page=('<!doctype html><html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="referrer" content="no-referrer"><title>'+html.escape(title)+' · Unfounded Theory</title><style>'+css+'</style></head><body><main><div class="brand">UNFOUNDED THEORY</div><section class="panel"><h1>'+html.escape(title)+'</h1>'+body+'</section><p class="help">Akses khusus pemilik AutoNews. Jangan bagikan password atau token.</p></main><script nonce="'+nonce+'">'+script+'</script></body></html>')
    return HTMLResponse(page,status_code=status_code,headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer','X-Content-Type-Options':'nosniff','Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-"+nonce+"'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"})

def _signature(data, secret):
    return hmac.new(secret.encode(),data.encode(),hashlib.sha256).hexdigest()

@router.get('/meta/connect')
def connect():
    try:
        _settings()
    except HTTPException:
        return _page('Pengaturan belum lengkap','<p>Server belum siap melakukan login Meta. Periksa enam Environment Variables di proyek Vercel <strong>autonews</strong> (Production), lalu Redeploy.</p>',status_code=503)
    return _page('Hubungkan Instagram',
       '<p>Hubungkan Facebook Page dan akun Instagram Professional melalui Meta.</p>'
       '<form method="post" action="/api/meta/connect">'
       '<label for="password">Password Admin AutoNews</label>'
       '<div class="field"><input id="password" name="password" type="password" required autocomplete="current-password" placeholder="Masukkan password admin">'
       '<button id="reveal" class="reveal" type="button" aria-pressed="false" aria-label="Lihat atau sembunyikan password">Lihat</button></div>'
       '<button class="primary" type="submit">Connect Instagram →</button></form>'
       '<p class="help">Gunakan password META_CONNECT_PASSWORD yang tersimpan di Vercel, bukan password Facebook.</p>')

@router.post('/meta/connect')
def connect_start(password:str=Form(...)):
    try:
        app_id,secret,admin,_,base,cfg=_settings()
    except HTTPException:
        return _page('Konfigurasi server belum siap','<p>Periksa enam variabel Vercel Production dan lakukan Redeploy.</p>',status_code=503)
    if not hmac.compare_digest(password,admin):
        return _page('Password tidak cocok',
            '<div class="alert">Password admin tidak sesuai dengan nilai META_CONNECT_PASSWORD pada Vercel Production.</div>'
            '<p>Periksa nilainya dan redeploy jika baru diubah.</p><a href="/api/meta/connect">← Coba lagi</a>',
            status_code=403)
    nonce=secrets.token_urlsafe(24)
    expiry=str(int(time.time())+TTL)
    state=nonce+'.'+expiry
    state=state+'.'+_signature(state,secret)
    redirect_uri=base+'/api/meta/callback'
    url='https://www.facebook.com/'+CONFIG.ig_version+'/dialog/oauth?'+urlencode({
        'client_id':app_id,'redirect_uri':redirect_uri,'state':state,
        'response_type':'code','config_id':cfg,'scope':SCOPES})
    response=RedirectResponse(url,status_code=303)
    response.set_cookie(COOKIE,state,max_age=TTL,httponly=True,secure=True,samesite='lax',path='/api/meta')
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
