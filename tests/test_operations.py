"""Operational regressions: worker scheduling, human-owned Telegram photos and readiness."""
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import pytest
from PIL import Image
from sqlalchemy.orm import sessionmaker
from utbot.models import Base, make_engine, Story, Draft
from utbot.research import fingerprint
from utbot import web, runner

@pytest.fixture
def db():
    engine=make_engine('sqlite://')
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine,expire_on_commit=False)() as session:
        yield session

class BotStub:
    def __init__(self):self.out=[]
    def message(self,chat,text,reply_markup=None):self.out.append(('msg',text))
    def answer(self,*args):pass
    def file_photo(self,*args,**kw):self.out.append(('image',str(args[1])))
    def download_photo(self,ident,path):
        Path(path).parent.mkdir(parents=True,exist_ok=True)
        Image.new('RGB',(1600,1400),(8,25,39)).save(path)
        return str(path)

def test_telegram_direct_photo_requires_attribution_and_new_approval(db,tmp_path,monkeypatch):
    source='https://science.nasa.gov/example-news/'
    st=Story(fingerprint=fingerprint(source),title='Astronomy report',source_url=source,source_name='NASA',topic='astronomy',
             verification_status='verified',evidence=[{'claim':'observed','url':source,'evidence_checked':True}])
    db.add(st);db.flush()
    dr=Draft(story_id=st.id,highlight='Inilah Tangan Tuhan, Struktur Sinar-X Raksasa Yang Masih Membingungkan NASA',
             caption='Para peneliti mengamati sinyal luar angkasa.\n\nNASA menjelaskannya.\n\nNamun ini masih memerlukan analisis.\n\nApa yang akan ditemukan berikutnya?',
             hashtags=['#NASA','#Sains','#Astronomi','#LuarAngkasa','#UnfoundedTheory'])
    db.add(dr);db.commit()
    cfg=replace(web.CONFIG,admin_ids=frozenset({42}),telegram_token='not-real',chat_id='100',media_dir=str(tmp_path))
    monkeypatch.setattr(web,'CONFIG',cfg)
    monkeypatch.setattr('utbot.media.CONFIG',cfg)
    bot=BotStub();monkeypatch.setattr(web,'_bot',lambda:bot)
    cb={'callback_query':{'id':'callback','from':{'id':42},'message':{'chat':{'id':100}},'data':f'photo:{dr.id}:1'}}
    assert web.telegram_webhook(cb,db=db)['ok']
    msg={'message':{'from':{'id':42},'chat':{'id':100},'photo':[{'file_id':'photo','width':1600,'height':1400}]}}
    response=web.telegram_webhook(msg,db=db)
    assert response['awaiting']=='photo_credit'
    assert dr.version==2 and dr.photo_license is None and not dr.rights_reviewed
    assert Path(dr.image_local_path).exists()
    bad={'message':{'from':{'id':42},'chat':{'id':100},'text':'bukan format'}}
    web.telegram_webhook(bad,db=db)
    assert dr.photo_license is None
    details={'message':{'from':{'id':42},'chat':{'id':100},'text':'Kredit: NASA Chandra\nLisensi: Public domain\nSumber: https://science.nasa.gov/example-news/'}}
    web.telegram_webhook(details,db=db)
    assert dr.photo_license == 'Public domain' and not dr.rights_reviewed
    cb['callback_query']['data']=f'rights:{dr.id}:{dr.version}'
    web.telegram_webhook(cb,db=db)
    assert dr.rights_reviewed
    assert dr.approved_version is None

def test_worker_loop_repeats_once_per_window(monkeypatch):
    invoked=[]
    monkeypatch.setattr(runner,'init_db',lambda:None)
    for name in ('do_discover','do_prepare','do_reschedule','do_publish'):
        monkeypatch.setattr(runner,name,lambda name=name: invoked.append(name))
    # Stop after 2 iterations; both in one 5-minute window.
    steps={'n':0}
    def fake_sleep(_):
        steps['n']+=1
        if steps['n']==2:raise StopIteration()
    with pytest.raises(StopIteration):
        runner.loop(sleep=fake_sleep,clock=lambda:datetime(2026,10,11,1,0,tzinfo=timezone.utc))
    assert invoked==['do_discover','do_prepare','do_reschedule','do_publish']

def test_readiness_reports_missing_connections_without_keys(db,monkeypatch):
    monkeypatch.setattr(web,'CONFIG',replace(web.CONFIG,ig_token='',telegram_token='',worker_secret=''))
    state=web.readiness(db=db)
    assert state['ready_for_live'] is False
    assert not state['checks']['instagram_credentials']
    assert not state['checks']['telegram_bot']
    assert 'worker_secret' in state['blockers']
    assert 'configured_ai' in state

def test_instagram_final_caption_omits_photo_credit_and_has_five_hashtags():
    from utbot.instagram import caption_text
    class D:
        caption='Sebuah penemuan baru.\n\nNASA menjelaskan hasilnya.'
        image_credit='NASA / Chandra'
        photo_license='Public domain'
        hashtags=['#Astronomi','#NASA','#Sains','#Antariksa','#UnfoundedTheory']
    message=caption_text(D)
    assert 'Foto:' not in message
    assert message.endswith('#UnfoundedTheory')
    assert sum(word.startswith('#') for word in message.split())==5
