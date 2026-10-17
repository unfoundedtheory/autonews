from datetime import datetime,timezone,timedelta
from dataclasses import replace
from sqlalchemy.orm import sessionmaker
import pytest
import httpx
from utbot.models import Base,make_engine,Story,Draft,Audit
from utbot.research import fingerprint
from utbot.editorial import approve
from utbot import web

@pytest.fixture
def db():
    eng=make_engine('sqlite://')
    Base.metadata.create_all(eng)
    with sessionmaker(bind=eng,expire_on_commit=False)() as ses:yield ses

def seeded(db):
    url='https://nasa.gov/test'
    s=Story(fingerprint=fingerprint(url),title='Test',source_url=url,source_name='NASA',
            topic='astronomy',verification_status='verified',evidence=[{'claim':'real','url':url,'evidence_checked':True}])
    db.add(s);db.flush()
    d=Draft(story_id=s.id,highlight='Ilmuwan Mengamati Fenomena Langit Yang Belum Terjelaskan Oleh Penelitian',
        caption='Satu pengamatan menjadi perhatian.\n\nNASA melaporkan hasilnya.\n\nNamun, hasilnya masih diuji.\n\nApa yang mungkin ditemukan berikutnya?',
        hashtags=['#NASA','#Astronomi','#Sains','#Langit','#UnfoundedTheory'],
        image_url='https://example.org/rendered.jpg',source_image_url='https://example.org/source.jpg',
        photo_license='CC0',image_credit='Example',rights_reviewed=False)
    db.add(d);db.commit();return d

class FakeBot:
    def __init__(self):self.sent=[]
    def answer(self,*a,**kw):self.sent.append(('answer',a))
    def message(self,chat,text,keyboard=None):self.sent.append(('message',chat,text))
    def file_photo(self,*a,**kw):self.sent.append(('photo',a))

def callback(d,action,user=42):
    return {'callback_query':{'id':'c-1','from':{'id':user},'message':{'chat':{'id':100}},
          'data':f'{action}:{d.id}:{d.version}'}}

def test_admin_one_click_approval_flow(db,monkeypatch):
    d=seeded(db)
    c=replace(web.CONFIG,admin_ids=frozenset({42}),telegram_token='local-token',daily_limit=2)
    monkeypatch.setattr(web,'CONFIG',c)
    bot=FakeBot()
    monkeypatch.setattr(web,'_bot',lambda:bot)
    assert web.telegram_webhook(callback(d,'approve',user=999),db=db)['ignored']=='not_allowlisted'
    web.telegram_webhook(callback(d,'approve'),db=db)
    assert d.status=='approved' and d.approved_version==d.version and d.scheduled_at
    assert any('disetujui' in item[2].lower() for item in bot.sent if item[0]=='message')


def test_instagram_container_waits_then_publishes_once(db,monkeypatch,tmp_path):
    d=seeded(db);d.rights_reviewed=True
    approve(db,d,'42')
    db.add(Audit(draft_id=d.id,event='photo_only_approved',actor='42',detail={'version':d.version}))
    d.scheduled_at=datetime.now(timezone.utc)-timedelta(minutes=1)
    db.commit()
    logo=tmp_path/'logo.png';logo.write_bytes(b'valid-placeholder-for-test')
    cfg=replace(web.CONFIG,photo_music_mode='off',live_publish=True,brand_logo=str(logo),ig_user_id='123',ig_token='token')
    monkeypatch.setattr(web,'CONFIG',cfg)
    monkeypatch.setattr(web,'_bot',lambda:None)
    class FakeIG:
        published_calls=0
        def __init__(self,*args):pass
        def create_container(self,url,caption):return 'container-1'
        def container_status(self,ident):return 'IN_PROGRESS' if self.published_calls==0 else 'FINISHED'
        def publish(self,ident):self.__class__.published_calls+=1;return 'media-id'
    # Initially in progress. Next run polls container and finalizes publish.
    monkeypatch.setattr(web,'InstagramPublisher',FakeIG)
    assert web.publish_job(db=db)['container_status']=='IN_PROGRESS'
    assert d.publish_state=='awaiting_container'
    FakeIG.published_calls=1
    assert web.publish_job(db=db)['published']==[d.id]
    assert d.publish_state=='published'
    assert web.publish_job(db=db)['due']==0

def test_uncertain_publish_never_retries(db,monkeypatch,tmp_path):
    d=seeded(db);d.rights_reviewed=True;approve(db,d,'42')
    db.add(Audit(draft_id=d.id,event='photo_only_approved',actor='42',detail={'version':d.version}))
    d.scheduled_at=datetime.now(timezone.utc)-timedelta(minutes=1)
    db.commit()
    logo=tmp_path/'logo.png';logo.write_bytes(b'placeholder')
    monkeypatch.setattr(web,'CONFIG',replace(web.CONFIG,photo_music_mode='off',live_publish=True,brand_logo=str(logo),ig_user_id='123',ig_token='token'))
    monkeypatch.setattr(web,'_bot',lambda:None)
    class BadIG:
        def __init__(self,*args):pass
        def create_container(self,*args):return 'container-2'
        def container_status(self,*args):return 'FINISHED'
        def publish(self,*args):raise httpx.TimeoutException('ambiguous request')
    monkeypatch.setattr(web,'InstagramPublisher',BadIG)
    assert web.publish_job(db=db)['status']=='uncertain'
    assert d.publish_state=='uncertain'
    assert web.publish_job(db=db)['due']==0


def test_telegram_approved_final_image_and_caption_reach_instagram_unchanged(db,monkeypatch,tmp_path):
    """Simulation uses the real approval webhook, then fake Meta API; no publication."""
    from utbot.instagram import caption_text
    d=seeded(db)
    d.rights_reviewed=True
    d.image_url='https://cdn.example.org/final-render-v1.jpg'
    db.commit()
    final_image=d.image_url
    final_caption=caption_text(d)
    logo=tmp_path/'brand-logo.png'
    logo.write_bytes(b'fake-logo')
    cfg=replace(web.CONFIG,admin_ids=frozenset({42}),telegram_token='mock-telegram',
        photo_music_mode='off',live_publish=True,brand_logo=str(logo),
        ig_user_id='123',ig_token='fake-meta-token')
    monkeypatch.setattr(web,'CONFIG',cfg)
    bot=FakeBot()
    monkeypatch.setattr(web,'_bot',lambda:bot)
    capture=[]
    class FakeIG:
        def __init__(self,*args):
            assert args[2:] == ('123','fake-meta-token')
        def create_container(self,url,caption):
            capture.append(('create',url,caption))
            return 'mock-container-id'
        def container_status(self,ident):
            assert ident=='mock-container-id'
            return 'IN_PROGRESS'
        def publish(self,ident):
            pytest.fail('Publishing must not occur while container remains IN_PROGRESS')
    monkeypatch.setattr(web,'InstagramPublisher',FakeIG)
    result=web.telegram_webhook(callback(d,'approve'),db=db)
    assert result['approval']=='approved_for_instagram'
    assert d.status=='approved' and d.approved_version==d.version
    assert capture==[('create',final_image,final_caption)]
    assert d.publish_state=='awaiting_container'
    # The scheduled cron can inspect the same container without duplicating creation.
    checked=web.publish_job(db=db)
    assert checked['container_status']=='IN_PROGRESS'
    assert capture==[('create',final_image,final_caption)]


def test_telegram_approved_dry_run_never_calls_instagram(db,monkeypatch):
    d=seeded(db)
    cfg=replace(web.CONFIG,admin_ids=frozenset({42}),telegram_token='mock-telegram',
                photo_music_mode='off',live_publish=False)
    monkeypatch.setattr(web,'CONFIG',cfg)
    monkeypatch.setattr(web,'_bot',lambda:FakeBot())
    assert web.telegram_webhook(callback(d,'approve'),db=db)
    assert d.approved_version==d.version
    class ForbiddenIG:
        def __init__(self,*args):
            pytest.fail('Instagram API should not be called with live_publish false')
    monkeypatch.setattr(web,'InstagramPublisher',ForbiddenIG)
    result=web.publish_job(db=db)
    assert result['live_publish'] is False
    assert d.status=='approved'
    assert d.publish_state=='unpublished'


def test_editorial_qc_telegram_message_readable():
    from utbot.web import format_editorial_qc
    class DraftStub:
        id='10e6b3e7-0000'
        version=3
    report={
       'passed':False,'status':'needs_manual_review',
       'issues':['CURIOSITY_GAP','qc_curiosity_gap'],
       'checks':{'curiosity_gap':{
          'passed':False,
          'unanswered_question':'Bagaimana bentuk asli lingkaran aurora?',
          'reason':'Highlight membuka jawabannya terlalu cepat.'}},
       'manual_checks':['fact_context','visual_accuracy','image_license']}
    message=format_editorial_qc(DraftStub(),report)
    assert '\n\n' in message
    assert 'STATUS: ⚠️ PERLU REVISI' in message
    assert '• qc curiosity gap' in message
    assert '🧾 PERIKSA MANUAL' in message
    assert '➡️ LANGKAH BERIKUTNYA' in message
    assert len(message)<=3900


def test_older_music_approval_cannot_autopost_after_switch_to_no_music(db,monkeypatch,tmp_path):
    draft=seeded(db)
    draft.rights_reviewed=True
    approve(db,draft,'42')  # Explicit earlier approval, but without photo-only consent event
    draft.scheduled_at=datetime.now(timezone.utc)-timedelta(minutes=1)
    db.commit()
    logo=tmp_path/'brand.png';logo.write_bytes(b'fake-logo-test')
    monkeypatch.setattr(web,'CONFIG',replace(web.CONFIG,
        photo_music_mode='off',live_publish=True,brand_logo=str(logo),
        ig_user_id='123',ig_token='mock'))
    monkeypatch.setattr(web,'_bot',lambda:None)
    class MustNotPublish:
        def __init__(self,*args):
            pytest.fail('Previous manual approval must never publish without photo-only consent')
    monkeypatch.setattr(web,'InstagramPublisher',MustNotPublish)
    assert web.publish_job(db=db)['due']==0
    assert draft.status=='approved' and draft.publish_state=='unpublished'
