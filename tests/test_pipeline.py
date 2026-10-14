from pathlib import Path
from datetime import datetime,timezone
import pytest
from PIL import Image
from sqlalchemy.orm import sessionmaker
from utbot.models import Base,make_engine,Story,Draft
from utbot.pipeline import normalize,check_evidence,prepare_story
from utbot.research import fingerprint
from utbot.editorial import approve,revise
from utbot.media import render_draft
from utbot.scheduler import schedule_approved,WIB

@pytest.fixture
def db():
    eng=make_engine('sqlite://')
    Base.metadata.create_all(eng)
    with sessionmaker(bind=eng,expire_on_commit=False)() as ses:yield ses

def _story(db):
    url='https://www.nasa.gov/some-official-science-report'
    s=Story(fingerprint=fingerprint(url),title='Report on space research',source_url=url,
            source_name='NASA',topic='astronomy',verification_status='needs_fact_check')
    db.add(s);db.flush();return s

def _data():
    return {'highlight':'Fisikawan Temukan Sinyal Aneh Dalam Pencarian Partikel Dark Matter',
        'caption':'Para ilmuwan melihat sesuatu yang tak biasa.\n\nNASA melaporkan hasil terbaru dari teleskop.\n\nNamun, temuan ini belum menjadi bukti final.\n\nApa lagi yang dapat diungkap oleh pengamatan berikutnya?',
        'hashtags':['#Astronomi','#NASA','#Sains','#Riset','#UnfoundedTheory'],
        'evidence':[{'claim':'tes observasi','quote':'The telescope took careful observations across several nights.'},
                    {'claim':'hasil perlu diuji','quote':'Scientists must still analyze the results before making claims.'}],
        'image_search':'dark matter telescope','accent_words':['Sinyal','Aneh']}

TEXT=normalize('The telescope took careful observations across several nights. Scientists must still analyze the results before making claims. ' * 9)

def test_evidence_exact_quotes(db):
    st=_story(db)
    assert len(check_evidence(_data(),st.source_url,TEXT))==2
    bad=_data();bad['evidence'][0]['quote']='Completely fictitious words added by the model'
    with pytest.raises(ValueError,match='kuti'):check_evidence(bad,st.source_url,TEXT)

def test_pipeline_drafts_unreviewed_rights_and_renders(db,tmp_path,monkeypatch):
    st=_story(db)
    monkeypatch.setattr('utbot.config.CONFIG',__import__('dataclasses').replace(__import__('utbot.config',fromlist=['CONFIG']).CONFIG,media_dir=str(tmp_path)))
    # media module imported CONFIG by value; monkeypatch both modules.
    from utbot.config import CONFIG
    monkeypatch.setattr('utbot.media.CONFIG',CONFIG)
    def fake_image(url,path):
        Path(path).parent.mkdir(parents=True,exist_ok=True)
        Image.new('RGB',(1600,1800),(30,60,130)).save(path)
        return str(path)
    opts=[{'image_url':'https://upload.wikimedia.org/abc.jpg','page_url':'https://commons.wikimedia.org/wiki/File:abc.jpg',
          'license':'CC BY 4.0','license_url':'https://creativecommons.org/licenses/by/4.0/',
          'credit':'Example photographer','title':'Telescope astronomy dark matter image'}]
    d=prepare_story(db,st,reader=lambda url:TEXT,writer=lambda s,t:(_data(),check_evidence(_data(),s.source_url,t)),
                    image_search=lambda q,limit:opts,image_intake=fake_image)
    assert st.verification_status=='verified' and len(st.evidence)==2
    assert d.image_local_path and Path(d.image_local_path).exists()
    assert Image.open(d.image_local_path).size==(1080,1350)
    assert d.image_url is None and not d.rights_reviewed
    approve(db,d,'42')
    assert d.rights_reviewed is False
    assert d.approved_version==1
    revise(db,d,'highlight','Sinyal Aneh Kembali Diamati Para Ilmuwan Dalam Pencarian Materi Gelap','42')
    assert d.approved_version is None
    render_draft(d)
    assert d.version==2 and Path(d.image_local_path).exists()

def test_queue_policy_day_caps(db):
    for i in range(7):
        st=_story(db) if i==0 else Story(fingerprint=str(i),title='x',source_url=f'https://nasa.gov/{i}',source_name='NASA',topic='astronomy',verification_status='verified')
        db.add(st);db.flush()
        st.verification_status='verified';st.evidence=[{'claim':'x','url':st.source_url,'evidence_checked':True}]
        d=Draft(story_id=st.id,highlight='Fisikawan Temukan Sinyal Aneh Dalam Pencarian Partikel Dark Matter',
                caption='Ada temuan baru.\n\nNASA menjelaskan.\n\nNamun tidak final.\n\nApa berikutnya?',
                hashtags=['#Astronomi','#NASA','#Sains','#Riset','#UnfoundedTheory'],
                rights_reviewed=True,image_url='https://example.org/ready.jpg',
                photo_license='CC0',image_credit='NASA')
        db.add(d);db.flush();approve(db,d,'owner')
    now=datetime(2026,10,9,17,tzinfo=timezone.utc)
    rows=schedule_approved(db,now=now,daily_limit=2)
    assert len(rows)==7
    ds=[db.get(Draft,r[0]) for r in rows]
    by_day={}
    for d in ds:
        if d.scheduled_at:
            day=d.scheduled_at.astimezone(WIB).date()
            by_day[day]=by_day.get(day,0)+1
    assert max(by_day.values())==2
    assert sorted(by_day.values())==[1,2,2,2]
