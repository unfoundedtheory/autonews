"""Meta API and native Instagram photo-music handoff regression suite."""
from dataclasses import replace
from datetime import datetime,timezone,timedelta
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy.orm import sessionmaker

from utbot.models import Base,make_engine,Story,Draft,Audit,TelegramSession
from utbot.meta import MetaGraph
from utbot.meta_delivery import publish_facebook_once
from utbot.photo_music import (instagram_post_url,manual_music_message,
                               manual_music_caption,mood_for)
from utbot.config import CONFIG
from utbot import web


def make_db():
    engine=make_engine('sqlite://')
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine,expire_on_commit=False)()


def approved_draft(db):
    st=Story(title='NASA Discovers an Ancient Galaxy',source_name='NASA',
             source_url='https://science.nasa.gov/universe/',topic='astronomy',
             fingerprint='f'*64,verification_status='verified')
    db.add(st);db.flush()
    d=Draft(story_id=st.id,version=1,
            highlight='Galaksi Purba Tersembunyi Di Antara Cahaya Alam Semesta',
            caption='Penemuan astronomi dari data NASA.\n\nIlmuwan mengamati galaksi kuno.\n\nTemuan ini masih terus diuji.\n\nApa yang akan ditemukan selanjutnya?',
            hashtags=['#Astronomi','#Galaksi','#NASA','#Sains','#UnfoundedTheory'],
            image_url='https://example.org/final-cover.jpg',image_credit='NASA',
            photo_license='Public domain',rights_reviewed=True,
            approved_version=1,approved_by='42',status='approved',
            publish_state='unpublished',
            scheduled_at=datetime.now(timezone.utc)-timedelta(minutes=5))
    db.add(d);db.commit()
    return st,d


def test_native_photo_music_handoff_and_permalink():
    db=make_db()
    try:
        st,d=approved_draft(db)
        msg=manual_music_message(d,st)
        assert 'feed foto 4:5' in msg
        assert 'Add music' in msg
        assert 'https://example.org/final-cover.jpg' in msg
        assert 'cosmic ambient' in msg
        assert 'Photo by : NASA' in manual_music_caption(d)
        assert mood_for('ai')=='minimal elektronik / cinematic tension'
        assert instagram_post_url('https://www.instagram.com/p/Cxyz_93/?igsh=1')==(
            'https://www.instagram.com/p/Cxyz_93/')
        for value in ('https://evil.example/p/C123','http://www.instagram.com/p/C123/',
                      'https://instagram.com/explore/','https://www.instagram.com/p/'):
            with pytest.raises(ValueError):
                instagram_post_url(value)
    finally:
        db.close()


def test_due_approval_sends_one_manual_handoff_without_meta_publish(monkeypatch):
    db=make_db()
    try:
        st,d=approved_draft(db)
        sent=[]
        class FakeBot:
            def message(self,chat_id,content,buttons=None):
                sent.append((chat_id,content,buttons))
                return {'message_id':len(sent)}
        monkeypatch.setattr(web,'TelegramClient',lambda *args:FakeBot())
        monkeypatch.setattr(web,'CONFIG',replace(CONFIG,photo_music_mode='manual',
                              telegram_token='test-token',chat_id='123',
                              live_publish=False))
        out=web.publish_job(db=db)
        assert out['manual_music']=='awaiting_editor'
        assert db.get(Draft,d.id).publish_state=='manual_music_pending'
        assert len(sent)==4
        assert 'PENGINGAT JADWAL POSTING' in sent[-1][1]
        assert 'CAPTION SIAP SALIN' in sent[1][1]
        assert sent[2][2]['inline_keyboard'][0][0]['callback_data'].startswith('musicdone:')
        assert web.publish_job(db=db)['manual_music']=='none_due'
        assert len(sent)==4
        assert db.query(Audit).filter_by(draft_id=d.id,event='manual_music_handoff').count()==1
    finally:
        db.close()


def test_manual_music_uses_known_photo_source_without_second_confirmation(monkeypatch):
    db=make_db()
    try:
        _,d=approved_draft(db)
        d.rights_reviewed=False
        d.photo_license=None
        d.image_credit=None
        d.media_page_url='https://science.nasa.gov/universe/'
        db.commit()
        sent=[]
        class FakeBot:
            def message(self,chat_id,message,buttons=None):
                sent.append(message)
        monkeypatch.setattr(web,'TelegramClient',lambda *args:FakeBot())
        monkeypatch.setattr(web,'CONFIG',replace(CONFIG,photo_music_mode='manual',
                              telegram_token='test-token',chat_id='123'))
        assert web.publish_job(db=db)['manual_music']=='awaiting_editor'
        assert d.publish_state=='manual_music_pending'
        assert 'Sumber gambar:' not in sent[1]
        assert 'https://science.nasa.gov/universe/' not in sent[1]
    finally:
        db.close()


def test_photo_music_mode_prevents_silent_photo_api_publication(monkeypatch):
    db=make_db()
    try:
        _,d=approved_draft(db)
        monkeypatch.setattr(web,'CONFIG',replace(CONFIG,photo_music_mode='manual',
                               telegram_token='',chat_id='',live_publish=True,
                               ig_user_id='1',ig_token='token'))
        monkeypatch.setattr(web,'InstagramPublisher',
                            lambda *args: (_ for _ in ()).throw(AssertionError('MUTE POST')))
        response=web.publish_job(db=db)
        assert response['manual_music']=='blocked'
        assert db.get(Draft,d.id).status=='approved'
    finally:
        db.close()


def test_meta_linkage_and_separate_facebook_page_post():
    calls=[]
    def reply(req):
        calls.append((req.method,req.url.path,dict(req.headers)))
        assert req.headers['authorization']=='Bearer test-token'
        if req.method=='GET':
            return httpx.Response(200,json={'id':'123','name':'UT Page',
                'instagram_business_account':{'id':'456'}})
        assert req.url.path.endswith('/123/photos')
        assert b'published=true' in req.content
        assert b'url=https' in req.content
        return httpx.Response(200,json={'id':'789','post_id':'123_789'})
    graph=MetaGraph('test-token',transport=httpx.MockTransport(reply))
    assert graph.page_linkage('123')['instagram_business_account_id']=='456'
    result=graph.publish_page_photo('123','https://example.com/a.jpg','Science caption')
    assert result=={'id':'123_789','photo_id':'789'}
    assert len(calls)==2


def test_meta_failure_does_not_leak_token():
    def bad(req):
        return httpx.Response(403,json={'error':{'message':'expired test-secret'}})
    graph=MetaGraph('test-secret',transport=httpx.MockTransport(bad))
    with pytest.raises(ValueError) as error:
        graph.page_linkage('123')
    assert 'test-secret' not in str(error.value)
    assert '403' in str(error.value)


def test_facebook_opt_in_idempotent_and_no_blind_retry():
    db=make_db()
    try:
        _,d=approved_draft(db)
        d.status='published';d.publish_state='published';db.commit()
        settings=replace(CONFIG,live_publish=True,facebook_crosspost=True,
                         facebook_page_id='123',facebook_page_token='secret')
        calls=[]
        fake=SimpleNamespace(publish_page_photo=lambda *args:
             (calls.append(args) or {'id':'123_123','photo_id':'123'}))
        first=publish_facebook_once(db,d,poster=fake,config=settings,actor='42')
        second=publish_facebook_once(db,d,poster=fake,config=settings,actor='42')
        assert first['facebook']=='published'
        assert second['facebook']=='already_attempted'
        assert len(calls)==1
        assert db.query(Audit).filter_by(draft_id=d.id,event='facebook_publish_started').count()==1
    finally:
        db.close()


def test_facebook_failure_requires_reconciliation():
    db=make_db()
    try:
        _,d=approved_draft(db)
        d.status='published';d.publish_state='published';db.commit()
        settings=replace(CONFIG,live_publish=True,facebook_crosspost=True,
                         facebook_page_id='123',facebook_page_token='secret')
        def fail(*args):raise httpx.ReadTimeout('unknown')
        fake=SimpleNamespace(publish_page_photo=fail)
        out=publish_facebook_once(db,d,poster=fake,config=settings)
        assert out['facebook']=='uncertain'
        assert publish_facebook_once(db,d,poster=fake,config=settings)['facebook']=='already_attempted'
        assert db.query(Audit).filter_by(draft_id=d.id,event='facebook_uncertain').count()==1
    finally:
        db.close()


@pytest.mark.parametrize('facebook_outcome', ['published', 'disabled', 'not_configured', 'uncertain', 'exception'])
def test_api_instagram_success_delivers_facebook_separately(monkeypatch, facebook_outcome):
    db=make_db()
    try:
        _,d=approved_draft(db)
        db.add(Audit(draft_id=d.id,event='photo_only_approved',actor='42',
                     detail={'version':d.version}))
        db.commit()
        settings=replace(CONFIG,photo_music_mode='off',live_publish=True,
                         ig_user_id='456',ig_token='test-token',
                         facebook_crosspost=True)
        monkeypatch.setattr(web,'CONFIG',settings)
        monkeypatch.setattr(web,'_bot',lambda:None)
        ig_calls=[]
        class FakeInstagram:
            def create_container(self,*args):return 'container-1'
            def container_status(self,*args):return 'FINISHED'
            def publish(self,*args):
                ig_calls.append(args)
                return 'ig-media-1'
        monkeypatch.setattr(web,'InstagramPublisher',lambda *a:FakeInstagram())
        fb_calls=[]
        def facebook(session,draft,**kwargs):
            assert draft.status==draft.publish_state=='published'
            assert draft.ig_media_id=='ig-media-1'
            assert kwargs['config'] is settings
            fb_calls.append(draft.id)
            if facebook_outcome=='exception':raise RuntimeError('Facebook unavailable')
            return {'facebook':facebook_outcome}
        monkeypatch.setattr(web,'publish_facebook_once',facebook)
        out=web.publish_job(db=db)
        assert out['instagram_media_id']=='ig-media-1'
        assert out['facebook']==('error' if facebook_outcome=='exception' else facebook_outcome)
        assert db.get(Draft,d.id).publish_state=='published'
        assert fb_calls==[d.id] and len(ig_calls)==1
        assert web.publish_job(db=db)=={'due':0}
        assert len(fb_calls)==len(ig_calls)==1
    finally:
        db.close()


def test_facebook_caption_allows_unknown_credit_without_inventing_one():
    db=make_db()
    try:
        _,d=approved_draft(db)
        d.status='published';d.publish_state='published';d.image_credit=None
        db.commit()
        settings=replace(CONFIG,live_publish=True,facebook_crosspost=True,
                         facebook_page_id='123',facebook_page_token='secret')
        sent=[]
        fake=SimpleNamespace(publish_page_photo=lambda page,image,caption:
            (sent.append(caption) or {'id':'123_789','photo_id':'789'}))
        out=publish_facebook_once(db,d,poster=fake,config=settings)
        assert out['facebook']=='published'
        assert d.caption in sent[0] and 'Photo by :' not in sent[0]
    finally:
        db.close()


def test_manual_ig_permalink_confirmed_via_telegram_without_api(monkeypatch):
    db=make_db()
    try:
        _,d=approved_draft(db)
        d.publish_state='manual_music_pending';db.commit()
        sent=[]
        bot=SimpleNamespace(
            message=lambda chat,msg,buttons=None:sent.append((chat,msg,buttons)),
            answer=lambda *args:None)
        monkeypatch.setattr(web,'_bot',lambda:bot)
        monkeypatch.setattr(web,'CONFIG',replace(CONFIG,admin_ids=frozenset({42}),
                              facebook_crosspost=False,live_publish=False))
        call={'callback_query':{'id':'cb1','from':{'id':42},
              'message':{'chat':{'id':123}},'data':f'musicdone:{d.id}:1'}}
        assert web.telegram_webhook(call,db=db)['ok']
        sess=db.get(TelegramSession,'42')
        assert sess and sess.mode=='music_post_link'
        confirm={'message':{'from':{'id':42},'chat':{'id':123},
                             'text':'https://www.instagram.com/p/C123TEST/'}}
        assert web.telegram_webhook(confirm,db=db)['ok']
        assert db.get(Draft,d.id).status=='published'
        assert db.get(Draft,d.id).ig_media_id is None
        assert db.query(Audit).filter_by(draft_id=d.id,event='ig_music_manual_confirmed').count()==1
        assert any('editor' not in x[1].lower() for x in sent)
    finally:
        db.close()


def test_facebook_uses_encrypted_oauth_page_connection(monkeypatch):
    from cryptography.fernet import Fernet
    from utbot.models import MetaConnection
    db=make_db()
    try:
        _,d=approved_draft(db)
        d.status='published';d.publish_state='published'
        encryption_key=Fernet.generate_key()
        monkeypatch.setenv('META_TOKEN_ENCRYPTION_KEY',encryption_key.decode())
        db.add(MetaConnection(page_id='123',instagram_id='456',
                              page_name='Unfounded Theory',
                              encrypted_page_token=Fernet(encryption_key).encrypt(b'oauth-page-token').decode()))
        db.commit()
        settings=replace(CONFIG,live_publish=True,facebook_crosspost=True,
                         facebook_page_id='',facebook_page_token='')
        calls=[]
        fake=SimpleNamespace(publish_page_photo=lambda page,image,caption:
             (calls.append((page,image,caption)) or {'id':'123_444','photo_id':'444'}))
        output=publish_facebook_once(db,d,poster=fake,config=settings)
        assert output['facebook']=='published'
        assert calls[0][0]=='123'
        assert publish_facebook_once(db,d,poster=fake,config=settings)['facebook']=='already_attempted'
        assert len(calls)==1
    finally:
        db.close()
