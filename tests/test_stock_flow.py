"""Guarded 24-hour fallback, stock replenishment and native music kit tests."""
from dataclasses import replace
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import sessionmaker

from utbot.config import CONFIG
from utbot.models import Base, make_engine, Story, Draft, Audit
from utbot.editorial import approve, editorial_guide_sha256
from utbot.quality_control import QC_RUBRIC_VERSION
from utbot.stock_flow import (
    auto_approve_overdue, is_auto_approved, stock_to_prepare, send_music_kit,
    dispatch_approved_kits, music_kit_sent,
)
from utbot import web


@pytest.fixture
def db():
    engine=make_engine('sqlite://')
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine,expire_on_commit=False)() as session:
        yield session


def seed(db, *, license='Public domain', commons=True, qc=True):
    url='https://science.nasa.gov/universe/'
    story=Story(fingerprint='abc123' + str(len(db.query(Story).all())),
        title='An unexpected cosmic phenomenon',source_url=url,
        source_name='NASA',topic='astronomy',verification_status='verified',
        evidence=[
            {'claim':'Observed by telescope','quote':'A structure was detected by scientists.',
             'url':url,'evidence_checked':True},
            {'claim':'Still being studied','quote':'Research will continue to test the idea.',
             'url':url,'evidence_checked':True}])
    db.add(story);db.flush()
    d=Draft(story_id=story.id,
        highlight='Inilah Tangan Tuhan, Struktur Sinar-X Raksasa Yang Masih Membingungkan NASA',
        caption=('Para peneliti memeriksa struktur sinar-X di angkasa.\n\n'
                 'NASA menjelaskan temuan tersebut berdasarkan pengamatan.\n\n'
                 'Namun, proses penelitian masih terus berlangsung.\n\n'
                 'Apa yang akan ditemukan dari struktur ini selanjutnya?'),
        hashtags=['#NASA','#Astronomi','#Sains','#Antariksa','#UnfoundedTheory'],
        image_url='https://example.org/cover-final.jpg',
        source_image_url=('https://upload.wikimedia.org/wikipedia/commons/a/test.jpg'
                          if commons else 'https://science.nasa.gov/media.jpg'),
        media_page_url=('https://commons.wikimedia.org/wiki/File:Test.jpg'
                        if commons else url),
        image_credit='NASA',photo_license=license,
        rights_reviewed=False,status='pending_approval',publish_state='unpublished')
    db.add(d);db.flush()
    if qc:
        checks={
            'curiosity_gap':{'passed':True,'reason':'Rasa penasaran tentang struktur sinar-X.',
                            'unanswered_question':'Bagaimana proses penemuan bentuk ini?'},
            'reader_relevance':{'passed':True,'reason':'Pengamatan antariksa membuat sains relevan.'},
            'caption_story':{'passed':True,'reason':'Caption bercerita dalam empat paragraf utuh.'},
            'fact_integrity':{'passed':True,'reason':'Klaim didukung oleh kutipan primer.'}}
        db.add(Audit(draft_id=d.id,event='editorial_qc',actor='worker',
                     detail={'version':d.version,'passed':True,
                       'status':'passed_automated','issues':[],
                       'style_review':'passed','checks':checks,
                       'guide_sha256':editorial_guide_sha256(),
                       'rubric_version':QC_RUBRIC_VERSION}))
    db.commit()
    return story,d


def config(tmp_path, **changes):
    logo=tmp_path/'brand.png';logo.write_bytes(b'logo')
    return replace(CONFIG,auto_approve_24h=True,photo_music_mode='manual',
                   live_publish=True,ig_user_id='1234',ig_token='secret',
                   brand_logo=str(logo),**changes)


def test_draft_stock_fills_gradually_without_unbounded_calls(db):
    opts=replace(CONFIG,draft_stock_target=14,prepare_batch_limit=3)
    assert stock_to_prepare(db,opts)==3
    for i in range(13):
        story=Story(fingerprint=str(i),title='T',source_url='https://nasa.gov/',
                    source_name='NASA')
        db.add(story);db.flush()
        db.add(Draft(story_id=story.id,highlight='Some news',caption='Text',
                     hashtags=[],status='pending_approval'))
    db.commit()
    assert stock_to_prepare(db,opts)==1
    _,last=seed(db,qc=False)
    assert stock_to_prepare(db,opts)==0
    last.status='rejected';db.commit()
    assert stock_to_prepare(db,opts)==1


def test_timeout_requires_elapsed_24h_qc_and_photo_rights(db,monkeypatch,tmp_path):
    monkeypatch.setattr('utbot.publication_guard.auto_visual_safe',lambda db,d,st:(True,'ok'))
    now=datetime.now(timezone.utc)
    _,d=seed(db)
    d.updated_at=now-timedelta(hours=23);db.commit()
    settings=config(tmp_path)
    assert auto_approve_overdue(db,now=now,config=settings)['approved']==[]
    d.updated_at=now-timedelta(hours=25);db.commit()
    result=auto_approve_overdue(db,now=now,config=settings)
    assert result['approved']==[d.id]
    assert d.approved_by=='system:24h_timeout'
    assert is_auto_approved(db,d)
    assert auto_approve_overdue(db,now=now,config=settings)['approved']==[]


def test_timeout_rejects_missing_qc_and_unclear_or_attribution_licenses(db,monkeypatch,tmp_path):
    monkeypatch.setattr('utbot.publication_guard.auto_visual_safe',lambda db,d,st:(True,'ok'))
    now=datetime.now(timezone.utc)
    settings=config(tmp_path)
    _,d=seed(db,license='CC BY 4.0')
    d.updated_at=now-timedelta(hours=26);db.commit()
    assert auto_approve_overdue(db,now=now,config=settings)['approved']==[]
    d.rights_reviewed=True
    db.commit()
    assert auto_approve_overdue(db,now=now,config=settings)['approved']==[]
    # For this eligibility unit test, move the last edit back past the deadline.
    d.updated_at=now-timedelta(hours=26)
    db.commit()
    assert auto_approve_overdue(db,now=now,config=settings)['approved']==[d.id]
    _,unclear=seed(db,commons=False)
    unclear.updated_at=now-timedelta(hours=27);db.commit()
    assert unclear.id in auto_approve_overdue(db,now=now,config=settings)['blocked']
    _,without_qc=seed(db,qc=False)
    without_qc.updated_at=now-timedelta(hours=27);db.commit()
    assert without_qc.id in auto_approve_overdue(db,now=now,config=settings)['blocked']


def test_timeout_disabled_without_live_ig_configuration(db,tmp_path):
    now=datetime.now(timezone.utc)
    _,d=seed(db)
    d.updated_at=now-timedelta(hours=26);db.commit()
    settings=config(tmp_path)
    assert not auto_approve_overdue(db,now=now,config=replace(settings,live_publish=False))['enabled']
    assert not auto_approve_overdue(db,now=now,config=replace(settings,ig_token=''))['enabled']
    assert d.status=='pending_approval'


class FakeBot:
    def __init__(self):self.messages=[];self.photos=[]
    def photo(self,chat,photo,caption):self.photos.append((chat,photo,caption))
    def message(self,chat,text,buttons=None):self.messages.append((chat,text,buttons))


def test_immediate_manual_music_kit_can_be_retrieved_and_reminded(db,monkeypatch):
    story,d=seed(db)
    approve(db,d,'42')
    d.scheduled_at=datetime.now(timezone.utc)-timedelta(minutes=2)
    db.commit()
    bot=FakeBot()
    assert send_music_kit(db,d,story,bot,'123')['kit']=='sent'
    assert len(bot.photos)==1
    assert len(bot.messages)==3
    assert 'CAPTION SIAP SALIN' in bot.messages[1][1]
    assert music_kit_sent(db,d)
    assert send_music_kit(db,d,story,bot,'123')['kit']=='already_sent'
    assert len(bot.messages)==3
    monkeypatch.setattr(web,'TelegramClient',lambda *args:bot)
    monkeypatch.setattr(web,'CONFIG',replace(CONFIG,photo_music_mode='manual',
                               telegram_token='test-token',chat_id='123',live_publish=False))
    out=web.publish_job(db=db)
    assert out['manual_music']=='awaiting_editor'
    assert d.publish_state=='manual_music_pending'
    assert len(bot.messages)==4
    assert 'PENGINGAT JADWAL' in bot.messages[-1][1]
    assert web.publish_job(db=db)['manual_music']=='none_due'
    assert len(bot.messages)==4


def test_legacy_approved_draft_gets_stock_kit_without_second_approval(db):
    st,d=seed(db)
    approve(db,d,'42');db.commit()
    bot=FakeBot()
    assert dispatch_approved_kits(db,bot,'123')['sent']==[d.id]
    assert dispatch_approved_kits(db,bot,'123')['sent']==[]
    assert d.status=='approved'


def test_auto_approved_photo_uses_graph_api_only_without_manual_handoff(db,monkeypatch,tmp_path):
    monkeypatch.setattr('utbot.publication_guard.auto_visual_safe',lambda db,d,st:(True,'ok'))
    st,d=seed(db)
    settings=config(tmp_path)
    now=datetime.now(timezone.utc)
    d.updated_at=now-timedelta(hours=26);db.commit()
    assert auto_approve_overdue(db,now=now,config=settings)['approved']==[d.id]
    d.scheduled_at=now-timedelta(minutes=1);db.commit()
    called=[]
    class Publisher:
        def __init__(self,*args):pass
        def create_container(self,url,caption):
            called.append(('create',url));return 'container1'
        def container_status(self,container):return 'FINISHED'
        def publish(self,container):
            called.append(('publish',container));return 'post123'
    monkeypatch.setattr(web,'InstagramPublisher',Publisher)
    monkeypatch.setattr(web,'CONFIG',replace(settings,telegram_token='test',
                                           chat_id='123'))
    monkeypatch.setattr(web,'TelegramClient',lambda *args:FakeBot())
    result=web.publish_job(db=db)
    assert result['instagram_media_id']=='post123'
    assert d.status=='published'
    assert len(called)==2
    assert web.publish_job(db=db).get('due')==0
