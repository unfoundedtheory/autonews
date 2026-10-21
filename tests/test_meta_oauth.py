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
        assert 'pages_manage_posts' in url['scope'][0].split(',')


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
        if request.url.path.endswith('/200/content_publishing_limit'):
            return httpx.Response(200,json={'data':[{'quota_usage':0}]})
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
        assert 'Akses API publikasi (kuota)' in res.text
        assert 'sensitive' not in res.text
        assert 'token' not in res.text.lower().split('<p>pengujian graph')[1].split('</p>')[0]


def test_container_test_is_gated_and_requires_valid_image(monkeypatch):
    from utbot import meta_oauth
    setup(monkeypatch)
    with TestClient(app) as client:
        assert client.get('/meta/test-container').status_code==200
        assert 'Tanpa Posting' in client.get('/meta/test-container').text
        invalid=client.post('/meta/test-container',data={
            'password':'wrong','image_url':'https://images.example.com/test.jpg','confirm':'yes'})
        assert invalid.status_code==403
        denied=client.post('/meta/test-container',data={
            'password':'test-dedicated-password','image_url':'http://localhost/secret','confirm':'yes'})
        assert denied.status_code==400
        assert 'Saya berhak menggunakan foto ini' not in client.get('/meta/test-container').text
        assert 'media_publish' not in denied.text

def test_container_url_rejects_private_ip_and_userinfo():
    import pytest
    from utbot.meta_oauth import _test_image_url
    for link in ('https://localhost/image.jpg','https://127.0.0.1/x.jpg',
                 'https://admin:pass@example.com/x.jpg','http://example.com/a.jpg'):
        with pytest.raises(ValueError):
            _test_image_url(link)
    assert _test_image_url('https://example.com/image.jpg')=='https://example.com/image.jpg'


def test_container_status_form_and_auth_gates(monkeypatch):
    setup(monkeypatch)
    from utbot.meta_oauth import _container_status_view
    page=_container_status_view('1234567890','IN_PROGRESS')
    assert 'Cek Status Container' in page.body.decode()
    assert '1234567890' in page.body.decode()
    assert 'media_publish' not in page.body.decode()
    with TestClient(app) as client:
        wrong=client.post('/meta/check-container',data={'password':'wrong','container_id':'1234567890'})
        assert wrong.status_code==403
        invalid=client.post('/meta/check-container',data={'password':'test-dedicated-password','container_id':'../media_publish'})
        assert invalid.status_code==400


def test_meta_callback_requires_posting_permission_and_page_content_task(monkeypatch):
    """New connections must prove both the requested scope and Page tasks."""
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool
    import httpx
    import pytest

    env=setup(monkeypatch)
    eng=create_engine('sqlite://',connect_args={'check_same_thread':False},
                      poolclass=StaticPool)
    Base.metadata.create_all(eng)
    factory=sessionmaker(bind=eng,expire_on_commit=False)
    monkeypatch.setattr(meta_oauth,'Session',factory)

    granted=True
    tasks=['CREATE_CONTENT']
    real_client=httpx.Client
    seen=[]
    def handler(request):
        nonlocal granted,tasks
        path=request.url.path
        seen.append((path,dict(request.url.params)))
        if path.endswith('/oauth/access_token'):
            if request.url.params.get('grant_type')=='fb_exchange_token':
                return httpx.Response(200,json={'access_token':'user-token'})
            return httpx.Response(200,json={'access_token':'short-token'})
        if path.endswith('/me/permissions'):
            assert request.headers['authorization']=='Bearer user-token'
            assert 'access_token' not in request.url.params
            return httpx.Response(200,json={'data':[
                {'permission':'pages_manage_posts',
                 'status':'granted' if granted else 'declined'}]})
        if path.endswith('/me/accounts'):
            assert request.headers['authorization']=='Bearer user-token'
            assert 'access_token' not in request.url.params
            assert 'tasks' in request.url.params['fields']
            return httpx.Response(200,json={'data':[{
                'id':'100','name':'Unfounded Theory','access_token':'page-token',
                'instagram_business_account':{'id':'200'},'tasks':tasks}]})
        raise AssertionError('Unexpected Graph endpoint: '+path)

    monkeypatch.setattr(meta_oauth.httpx,'Client',
                        lambda *args,**kwargs:real_client(transport=httpx.MockTransport(handler)))

    def connect():
        return meta_oauth._complete_callback(None,env['META_APP_ID'],
            env['META_APP_SECRET'],env['META_TOKEN_ENCRYPTION_KEY'],
            env['META_OAUTH_BASE_URL'],'authorization-code')

    # Missing pages_manage_posts cannot overwrite previously saved connection.
    with factory() as db:
        existing=MetaConnection(page_id='100',instagram_id='200',page_name='Unfounded Theory',
            encrypted_page_token=Fernet(env['META_TOKEN_ENCRYPTION_KEY'].encode()).encrypt(
                b'original-page-token').decode())
        db.add(existing)
        db.commit()
        encrypted_before=existing.encrypted_page_token

    granted=False
    with pytest.raises(meta_oauth.MetaStageError) as error:
        connect()
    assert error.value.stage=='page_permissions'
    assert error.value.category=='pages_manage_posts'
    with factory() as db:
        assert db.get(MetaConnection,'100').encrypted_page_token==encrypted_before
    assert not any(p.endswith('/me/accounts') for p,_ in seen)

    # Permission granted but no CREATE_CONTENT: no token rotation.
    granted=True
    tasks=['ANALYZE','ADVERTISE']
    response=connect()
    assert response.status_code==403
    assert 'CREATE_CONTENT' in response.body.decode()
    with factory() as db:
        assert db.get(MetaConnection,'100').encrypted_page_token==encrypted_before

    # Correct permission and Page tasks -> encrypted new Page token.
    tasks=['CREATE_CONTENT','ANALYZE']
    response=connect()
    assert response.status_code==200
    assert 'page-token' not in response.body.decode()
    with factory() as db:
        row=db.get(MetaConnection,'100')
        assert row.encrypted_page_token!=encrypted_before
        assert Fernet(env['META_TOKEN_ENCRYPTION_KEY'].encode()).decrypt(
            row.encrypted_page_token.encode())==b'page-token'


def test_page_content_tasks_support_current_and_legacy_graph_response():
    assert meta_oauth._page_can_publish({'tasks':['CREATE_CONTENT']})
    assert meta_oauth._page_can_publish({'tasks':['PROFILE_PLUS_CREATE_CONTENT']})
    assert meta_oauth._page_can_publish({'tasks':['PROFILE_PLUS_FULL_CONTROL']})
    assert not meta_oauth._page_can_publish({'tasks':['ANALYZE']})
    assert not meta_oauth._page_can_publish({})
