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


def test_meta_stage_error_masks_sensitive_message():
    from utbot.meta_oauth import _get, MetaStageError
    import httpx
    def graph_handler(request):
        return httpx.Response(400,json={'error':{'message':'private-token-do-not-log',
                                                 'code':190,'error_subcode':463}})
    with httpx.Client(transport=httpx.MockTransport(graph_handler)) as client:
        try:
            _get(client,'https://graph.facebook.com/v24.0/me/accounts',{},'page_lookup')
        except MetaStageError as exc:
            assert exc.stage=='page_lookup'
            assert exc.status==400
            assert exc.code==190
            assert exc.subcode==463
            assert 'private-token' not in str(exc)
        else:
            assert False, 'Expected staged failure'


def test_meta_error_categories_never_echo_raw_response():
    from utbot.meta_oauth import _classify_meta_failure, _get, MetaStageError
    import httpx
    assert _classify_meta_failure({'message':'Error validating verification code'})=='authorization_code'
    assert _classify_meta_failure({'message':'Redirect URI does not match'})=='redirect_uri'
    assert _classify_meta_failure({'message':'Invalid App Secret'})=='app_secret'
    def handle(request):
        return httpx.Response(400,json={'error':{'code':1,'message':'Redirect URI mismatch secret-secret'}})
    with httpx.Client(transport=httpx.MockTransport(handle)) as c:
        try:
            _get(c,'https://graph.facebook.com/v24.0/oauth/access_token',{},'code_exchange')
        except MetaStageError as exc:
            assert exc.category=='redirect_uri'
            assert 'secret-secret' not in str(exc)
        else:
            assert False


def test_multi_page_selection_is_encrypted_and_one_time(monkeypatch):
    import json
    from datetime import datetime,timezone,timedelta
    from sqlalchemy.orm import sessionmaker
    from utbot.models import MetaPageChoice
    from utbot import meta_oauth
    from fastapi.testclient import TestClient
    env=setup(monkeypatch)
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool
    eng=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(eng)
    test_session=sessionmaker(bind=eng,expire_on_commit=False)
    monkeypatch.setattr(meta_oauth,'Session',test_session)
    options=[{'id':'100','name':'Unfounded Theory','instagram_id':'800','token':'secret-a'},
             {'id':'200','name':'Other Page','instagram_id':'900','token':'secret-b'}]
    id='safe-choice-id'
    encrypted=Fernet(env['META_TOKEN_ENCRYPTION_KEY'].encode()).encrypt(json.dumps(options).encode()).decode()
    with test_session() as db:
        db.add(MetaPageChoice(id=id,encrypted_candidates=encrypted,
                              expires_at=datetime.now(timezone.utc)+timedelta(minutes=5)))
        db.commit()
    with TestClient(app) as client:
        client.cookies.set(meta_oauth.CHOICE_COOKIE,id,path='/meta')
        denied=client.post('/meta/select-page',data={'page_id':'999'})
        assert denied.status_code==403
        selected=client.post('/meta/select-page',data={'page_id':'100'})
        assert selected.status_code==200
        assert 'Unfounded Theory' in selected.text
        assert 'secret-a' not in selected.text
        assert 'secret-b' not in selected.text
        again=client.post('/meta/select-page',data={'page_id':'100'})
        assert again.status_code==403
        with test_session() as db:
            stored=db.get(MetaConnection,'100')
            assert stored.instagram_id=='800'
            assert 'secret-a' not in stored.encrypted_page_token
            assert db.get(MetaConnection,'200') is None


def test_meta_read_only_test_requires_admin(monkeypatch):
    setup(monkeypatch)
    with TestClient(app) as client:
        assert client.get('/meta/test').status_code==200
        bad=client.post('/meta/test',data={'password':'wrong'})
        assert bad.status_code==403
        assert 'Password admin tidak cocok' in bad.text


def test_meta_read_only_test_with_mocked_graph(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool
    from sqlalchemy.orm import sessionmaker
    from utbot import meta_oauth
    from utbot.models import MetaConnection
    import httpx
    env=setup(monkeypatch)
    eng=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(eng)
    session_factory=sessionmaker(bind=eng,expire_on_commit=False)
    with session_factory() as db:
        db.add(MetaConnection(page_id='100',instagram_id='200',page_name='Unfounded Theory',
            encrypted_page_token=Fernet(env['META_TOKEN_ENCRYPTION_KEY'].encode()).encrypt(b'token').decode()))
        db.commit()
    monkeypatch.setattr(meta_oauth,'Session',session_factory)
    real_client=httpx.Client
    def handler(request):
        assert request.method=='GET'
        assert request.headers['authorization']=='Bearer token'
        if request.url.path.endswith('/100'):
            if 'access_token' in request.url.params.get('fields',''):
                return httpx.Response(200,json={'access_token':'sensitive'})
            return httpx.Response(200,json={'id':'100','name':'Unfounded Theory','instagram_business_account':{'id':'200'}})
        return httpx.Response(200,json={'id':'200','username':'unfoundedtheory','account_type':'BUSINESS'})
    def fake_client(*args,**kwargs):
        return real_client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(meta_oauth.httpx,'Client',fake_client)
    with TestClient(app) as client:
        res=client.post('/meta/test',data={'password':'test-dedicated-password'})
        assert res.status_code==200
        assert 'Hasil Tes Koneksi' in res.text
        assert 'sensitive' not in res.text
        assert 'token' not in res.text.lower().split('<p>pengujian graph')[1].split('</p>')[0]
