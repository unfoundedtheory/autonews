"""Meta owner connection safeguards without external Meta requests."""
from dataclasses import replace
from urllib.parse import urlparse,parse_qs
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from utbot.meta_oauth import router, COOKIE
from utbot.web import app
from utbot.models import Base, make_engine, MetaConnection
from utbot import meta_oauth
from sqlalchemy.orm import sessionmaker


def setup(monkeypatch):
    env={
        'META_APP_ID':'12345678',
        'META_APP_SECRET':'dev-secret',
        'META_CONNECT_PASSWORD':'test-dedicated-password',
        'META_TOKEN_ENCRYPTION_KEY':Fernet.generate_key().decode(),
        'META_LOGIN_CONFIG_ID':'1845302206633686',
        'META_OAUTH_BASE_URL':'https://unfoundedtheory.vercel.app',
    }
    for k,v in env.items():monkeypatch.setenv(k,v)
    return env


def test_meta_connect_requires_secrets(monkeypatch):
    for k in ('META_APP_ID','META_APP_SECRET','META_CONNECT_PASSWORD',
              'META_LOGIN_CONFIG_ID','META_TOKEN_ENCRYPTION_KEY'):
        monkeypatch.delenv(k,raising=False)
    with TestClient(app) as client:
        res=client.get('/meta/connect')
        assert res.status_code==503


def test_connect_rejects_wrong_password_and_has_correct_redirect(monkeypatch):
    setup(monkeypatch)
    with TestClient(app) as client:
        assert client.get('/meta/connect').status_code==200
        invalid=client.post('/meta/connect',data={'password':'wrong'},follow_redirects=False)
        assert invalid.status_code==403
        response=client.post('/meta/connect',data={'password':'test-dedicated-password'},
                             follow_redirects=False)
        assert response.status_code==303
        assert 'httponly' in response.headers['set-cookie'].lower()
        assert 'secure' in response.headers['set-cookie'].lower()
        url=parse_qs(urlparse(response.headers['location']).query)
        assert url['redirect_uri']==['https://unfoundedtheory.vercel.app/api/meta/callback']
        assert url['config_id']==['1845302206633686']
        assert 'META_APP_SECRET' not in response.headers['location']
        assert url['client_id']==['12345678']


def test_callback_state_blocks_without_cookie_or_wrong_nonce(monkeypatch):
    setup(monkeypatch)
    with TestClient(app) as client:
        assert client.get('/meta/callback?state=bogus&code=fake').status_code==400
        response=client.post('/meta/connect',data={'password':'test-dedicated-password'},
                             follow_redirects=False)
        state=parse_qs(urlparse(response.headers['location']).query)['state'][0]
        assert client.get('/meta/callback',params={'state':state+'x','code':'fake'}).status_code==400


def test_token_is_encrypted_at_rest():
    eng=make_engine('sqlite://')
    Base.metadata.create_all(eng)
    with sessionmaker(bind=eng)() as db:
        key=Fernet.generate_key()
        item=MetaConnection(page_id='456',instagram_id='789',page_name='Page',
                            encrypted_page_token=Fernet(key).encrypt(b'test-token').decode())
        db.add(item);db.commit()
        db.refresh(item)
        assert 'test-token' not in item.encrypted_page_token
        assert Fernet(key).decrypt(item.encrypted_page_token.encode())==b'test-token'


def test_connect_fetch_reports_password_error_and_oauth_redirect(monkeypatch):
    setup(monkeypatch)
    with TestClient(app) as client:
        bad=client.post('/meta/connect',data={'password':'wrong'},
            headers={'X-Requested-With':'AutoNewsConnect','Accept':'application/json'})
        assert bad.status_code==403
        assert 'Password' in bad.json()['message']
        good=client.post('/meta/connect',data={'password':'test-dedicated-password'},
            headers={'X-Requested-With':'AutoNewsConnect','Accept':'application/json'})
        assert good.status_code==200
        assert good.json()['redirect_url'].startswith('https://www.facebook.com/')
        assert COOKIE in good.headers['set-cookie']
        assert good.headers['cache-control']=='no-store'


def test_meta_page_csp_allows_same_origin_ajax(monkeypatch):
    setup(monkeypatch)
    with TestClient(app) as client:
        res=client.get('/meta/connect')
        assert res.status_code==200
        csp=res.headers['content-security-policy']
        assert "connect-src 'self'" in csp
        assert "default-src 'none'" in csp
