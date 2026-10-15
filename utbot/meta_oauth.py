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
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
import logging

log=logging.getLogger(__name__)
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
    css="""*{box-sizing:border-box}html{color-scheme:light}body{margin:0;min-height:100vh;display:grid;place-items:center;padding:24px;font:15px/1.6 system-ui,-apple-system,sans-serif;color:#20202b;background:radial-gradient(ellipse at 5% 0%,#ffe3b6 0%,transparent 43%),radial-gradient(ellipse at 98% 95%,#e0c5ff 0%,transparent 48%),#fff7fb}main{width:min(100%,440px)}.brand{display:flex;gap:10px;align-items:center;font-weight:900;letter-spacing:.07em;font-size:14px;margin-bottom:24px}.mark{height:37px;width:37px;display:grid;place-items:center;border-radius:12px;color:white;font-size:20px;background:linear-gradient(35deg,#feda75,#fa7e1e 22%,#d62976 54%,#962fbf 80%,#4f5bd5)}.panel{padding:clamp(24px,6vw,40px);border:1px solid #f2e4ed;border-radius:22px;background:#fff;box-shadow:0 28px 70px #672c5b18}h1{font-size:clamp(25px,5vw,30px);letter-spacing:-.04em;line-height:1.25;margin:0 0 12px;color:#20202b}p{color:#686678;margin:0 0 22px}label{display:block;font-weight:700;font-size:14px;margin-bottom:8px}.field{display:flex;align-items:center;border:1px solid #d9d3de;border-radius:12px;overflow:hidden;background:#fff}.field:focus-within{outline:2px solid #b8328a;border-color:transparent}input{width:100%;flex:1;min-width:0;border:0;outline:0;padding:14px;font:inherit;color:#21212b;background:transparent}button{font:inherit;cursor:pointer}.reveal{border:0;background:none;color:#a32982;padding:12px;font-weight:700;min-width:86px}.primary{width:100%;border:0;border-radius:12px;padding:14px;margin-top:18px;color:#fff;background:linear-gradient(90deg,#f58529,#dd2a7b 52%,#8134af);font-weight:800;box-shadow:0 8px 20px #cf3a8938}.primary:hover{filter:brightness(.97)}.primary:disabled{opacity:.75;cursor:wait}.help{font-size:13px;color:#777181;margin:15px 0 0}.alert{background:#fff1f5;border:1px solid #fac3d8;padding:14px;border-radius:12px;color:#8c184f;margin:0 0 18px}.notice{font-size:13px;color:#8c235f;min-height:20px;margin:12px 0 0}.foot{margin:20px auto;text-align:center;color:#777181;font-size:12px}a{color:#a32982;font-weight:700}.status{display:inline-flex;gap:6px;align-items:center;background:#f7f2f8;color:#7a447a;border-radius:100px;padding:5px 12px;margin-bottom:16px;font-size:12px;font-weight:700}@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto}}"""
    script="""const b=document.getElementById('reveal'),p=document.getElementById('password'),f=document.getElementById('connect-form'),msg=document.getElementById('submit-state'),btn=document.getElementById('submit-btn');
if(b&&p){b.addEventListener('click',()=>{let v=p.type==='password';p.type=v?'text':'password';b.textContent=v?'Sembunyikan':'Lihat';b.setAttribute('aria-pressed',String(v));});}
if(f&&p&&msg&&btn){f.addEventListener('submit',async ev=>{ev.preventDefault();if(!p.value.trim()){msg.textContent='Masukkan password admin terlebih dahulu.';return;}btn.disabled=true;btn.textContent='Memeriksa…';msg.textContent='Memeriksa koneksi server…';let ctl=new AbortController();let clock=setTimeout(()=>ctl.abort(),20000);try{const res=await fetch(f.action,{method:'POST',body:new FormData(f),headers:{'X-Requested-With':'AutoNewsConnect','Accept':'application/json'},credentials:'same-origin',redirect:'manual',signal:ctl.signal});if(res.type==='opaqueredirect'){msg.textContent='Server melakukan redirect; melanjutkan login…';f.submit();return;}let data={};try{data=await res.json()}catch(e){msg.textContent='Server merespons HTTP '+res.status+' tetapi format respons tidak sesuai. Screenshot pesan ini.';return;}if(!res.ok){msg.textContent=(data.message||'Koneksi ditolak')+' (HTTP '+res.status+').';return;}if(data.redirect_url&&data.redirect_url.startsWith('https://www.facebook.com/')){msg.textContent='Membuka halaman Facebook…';window.location.assign(data.redirect_url);return;}msg.textContent='Respons server tidak memiliki URL login (HTTP '+res.status+').';}catch(e){msg.textContent=e.name==='AbortError'?'Server tidak merespons dalam 20 detik. Coba lagi atau periksa Vercel Logs.':'Koneksi ke server gagal: '+e.name+'. Periksa jaringan/browser.';}finally{clearTimeout(clock);btn.disabled=false;btn.textContent='Hubungkan Instagram →';}});}
"""
    page=('<!doctype html><html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="referrer" content="no-referrer"><title>'+html.escape(title)+' · Unfounded Theory</title><style>'+css+'</style></head><body><main><div class="brand">UNFOUNDED THEORY</div><section class="panel"><h1>'+html.escape(title)+'</h1>'+body+'</section><p class="help">Akses khusus pemilik AutoNews. Jangan bagikan password atau token.</p></main><script nonce="'+nonce+'">'+script+'</script></body></html>')
    return HTMLResponse(page,status_code=status_code,headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer','X-Content-Type-Options':'nosniff','Content-Security-Policy':"default-src 'none'; connect-src 'self'; style-src 'unsafe-inline'; script-src 'nonce-"+nonce+"'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"})

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
       '<div class="status">● Koneksi Meta · Pemilik</div><form id="connect-form" method="post" action="/api/meta/connect">'
       '<label for="password">Password Admin AutoNews</label>'
       '<div class="field"><input id="password" name="password" type="password" required autocomplete="current-password" placeholder="Masukkan password admin">'
       '<button id="reveal" class="reveal" type="button" aria-pressed="false" aria-label="Lihat atau sembunyikan password">Lihat</button></div>'
       '<button id="submit-btn" class="primary" type="submit">Hubungkan Instagram →</button><div class="notice" id="submit-state" role="status" aria-live="polite"></div></form>'
       '<p class="help">Gunakan password META_CONNECT_PASSWORD yang tersimpan di Vercel, bukan password Facebook.</p>')

@router.post('/meta/connect')
def connect_start(request:Request,password:str=Form(...)):
    wants_json=request.headers.get('x-requested-with')=='AutoNewsConnect'
    try:
        app_id,secret,admin,_,base,cfg=_settings()
    except HTTPException:
        if wants_json:
            return JSONResponse({'message':'Konfigurasi server belum lengkap. Periksa Vercel Production.'},status_code=503)
        return _page('Konfigurasi server belum siap','<p>Periksa enam variabel Vercel Production dan lakukan Redeploy.</p>',status_code=503)
    if not hmac.compare_digest(password,admin):
        if wants_json:
            return JSONResponse({'message':'Password admin salah. Pastikan sesuai META_CONNECT_PASSWORD di Vercel.'},status_code=403)
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
    response=(JSONResponse({'redirect_url':url},status_code=200) if wants_json
              else RedirectResponse(url,status_code=303))
    response.set_cookie(COOKIE,state,max_age=TTL,httponly=True,secure=True,samesite='lax',path='/api/meta')
    response.headers['Cache-Control']='no-store'
    return response

class MetaStageError(Exception):
    def __init__(self,stage,status,code=None,subcode=None):
        self.stage=stage
        self.status=status
        self.code=code
        self.subcode=subcode
        super().__init__(stage)


def _get(client,url,params,stage):
    res=client.get(url,params=params,timeout=20,follow_redirects=False)
    if res.is_error:
        try:
            failure=res.json().get('error',{})
            code=failure.get('code') if isinstance(failure,dict) else None
            subcode=failure.get('error_subcode') if isinstance(failure,dict) else None
        except (ValueError,TypeError):
            code=subcode=None
        raise MetaStageError(stage,res.status_code,code,subcode)
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
    try:
        return _complete_callback(request,app_id,secret,encryption,base,code)
    except MetaStageError as exc:
        stages={'code_exchange':'menukar kode login menjadi token',
                'long_lived_exchange':'memperpanjang masa berlaku token',
                'page_lookup':'mencari Facebook Page dan Instagram tertaut'}
        description=stages.get(exc.stage,'memproses otorisasi')
        details='HTTP '+str(exc.status)
        if isinstance(exc.code,int):
            details+=' · Meta code '+str(exc.code)
        if isinstance(exc.subcode,int):
            details+=' · subcode '+str(exc.subcode)
        log.warning('Meta OAuth stage=%s http=%s code=%s subcode=%s',
                    exc.stage,exc.status,exc.code,exc.subcode)
        return _page('Meta menolak permintaan',
          '<p>Login Facebook berhasil, tetapi Meta menolak saat '+html.escape(description)+'.</p>'
          '<div class="alert">'+html.escape(details)+'</div>'
          '<p>Kirim screenshot kode error ini (bukan URL/token) untuk menentukan perbaikan berikutnya.</p>'
          '<a href="/api/meta/connect">← Coba lagi</a>',status_code=502)
    except (httpx.HTTPError,ValueError,KeyError,TypeError) as exc:
        log.warning('Meta OAuth callback failure: %s',type(exc).__name__)
        return _page('Proses koneksi belum berhasil','<p>Terjadi kesalahan ketika membaca respons dari Meta. Token tidak ditampilkan atau disimpan secara parsial.</p><a href="/api/meta/connect">← Coba lagi</a>',status_code=502)
    except SQLAlchemyError as exc:
        log.error('Meta OAuth DB persistence failed: %s',type(exc).__name__)
        return _page('Database belum siap','<p>Login Facebook berhasil, tetapi koneksi tidak dapat disimpan ke database AutoNews. Periksa migrasi tabel meta_connections dan DATABASE_URL di Vercel.</p>',status_code=503)


def _complete_callback(request,app_id,secret,encryption,base,code):
    with httpx.Client() as client:
        raw=_get(client,'https://graph.facebook.com/'+CONFIG.ig_version+'/oauth/access_token',{
            'client_id':app_id,'client_secret':secret,'redirect_uri':base+'/api/meta/callback',
            'code':code},'code_exchange')
        short=raw.get('access_token')
        if not short:raise HTTPException(502,'Meta did not return an access token')
        exchanged=_get(client,'https://graph.facebook.com/'+CONFIG.ig_version+'/oauth/access_token',{
            'grant_type':'fb_exchange_token','client_id':app_id,
            'client_secret':secret,'fb_exchange_token':short},'long_lived_exchange')
        user_token=exchanged.get('access_token')
        if not user_token:raise HTTPException(502,'Meta token exchange failed')
        accounts=_get(client,'https://graph.facebook.com/'+CONFIG.ig_version+'/me/accounts',{
            'fields':'id,name,access_token,instagram_business_account',
            'access_token':user_token,'limit':100},'page_lookup').get('data',[])
    if not isinstance(accounts,list):
        raise ValueError('Unexpected Page list response')
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
