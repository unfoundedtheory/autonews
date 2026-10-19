"""Prove website planned posts are real, locked, version-bound and safe."""
from dataclasses import replace
from datetime import datetime,timedelta,timezone
import pytest
from sqlalchemy.orm import sessionmaker
from utbot.models import Base,make_engine,Story,Draft,Audit
from utbot.research import fingerprint
from utbot.scheduler import WIB,schedule_approved
from utbot import planner_scheduling as schedule


def newsroom(db):
    url='https://science.nasa.gov/universe/galaxies/'
    story=Story(fingerprint=fingerprint(url),title='NASA galaxy photo',
                source_url=url,source_name='NASA',topic='astronomy',
                verification_status='verified',evidence=[
        {'claim':'NASA observation','quote':'Source excerpt','url':url,'evidence_checked':True},
        {'claim':'Galaxy near us','quote':'Second excerpt','url':url,'evidence_checked':True},
    ])
    db.add(story);db.flush()
    draft=Draft(story_id=story.id,
                highlight='Galaksi Terdekat Ini Ternyata Menyimpan Fenomena Langka',
                caption='Paragraf satu.\n\nParagraf dua.\n\nParagraf tiga.\n\nMengapa demikian?',
                hashtags=['#Astronomi','#NASA','#Antariksa','#Riset','#UnfoundedTheory'],
                image_url='https://media.example.org/final-cover.jpg',
                image_credit='NASA',photo_license='Public domain',
                rights_reviewed=True)
    db.add(draft);db.commit()
    return draft


def tomorrow_slot(hour=12):
    day=datetime.now(WIB).date()+timedelta(days=2)
    return datetime(day.year,day.month,day.day,hour,tzinfo=WIB)


def test_web_calendar_is_real_auto_post_queue_and_protected_against_rescheduler(monkeypatch):
    monkeypatch.setattr(schedule,'CONFIG',replace(schedule.CONFIG,live_publish=True))
    monkeypatch.setattr(schedule,'report_for_draft',lambda db,d,st:
                        {'passed':True,'style_review':'passed'})
    engine=make_engine('sqlite://')
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine,expire_on_commit=False)() as db:
        d=newsroom(db)
        at=tomorrow_slot()
        saved=schedule.schedule_web_post(db,d,at)
        db.commit()
        assert saved==at.astimezone(timezone.utc)
        assert d.status=='approved' and d.approved_version==d.version
        assert d.scheduled_at==saved
        assert schedule.planner_photo_only(db,d)
        assert schedule.pinned_planner_schedule(db,d)
        schedule_approved(db)
        assert d.scheduled_at==saved, 'Routine queue must not overwrite calendar slot'
        with pytest.raises(ValueError,match='Slot'):
            other=newsroom_other(db)
            schedule.schedule_web_post(db,other,at)
        db.rollback()
        schedule.unschedule_web_post(db,d)
        db.commit()
        assert not schedule.planner_photo_only(db,d)
        assert d.scheduled_at is None and d.status=='pending_approval'


def newsroom_other(db):
    base=db.query(Story).first()
    url=base.source_url+'?other=true'
    st=Story(fingerprint=fingerprint(url),title=base.title+' B',source_url=url,
             source_name=base.source_name,topic='astronomy',
             verification_status='verified',evidence=base.evidence)
    db.add(st);db.flush()
    d=Draft(story_id=st.id,highlight='Galaksi Kedua Tampak Sangat Terang Dari Bumi',
            caption='Satu.\n\nDua.\n\nTiga.\n\nApa ini?',
            hashtags=['#Astronomi','#NASA','#Antariksa','#Riset','#UnfoundedTheory'],
            image_url='https://media.example.org/another-cover.jpg',image_credit='NASA',
            photo_license='Public domain',rights_reviewed=True)
    db.add(d);db.commit()
    return d


def test_unsafe_photo_or_missing_ai_qc_never_schedules(monkeypatch):
    monkeypatch.setattr(schedule,'CONFIG',replace(schedule.CONFIG,live_publish=True))
    monkeypatch.setattr(schedule,'report_for_draft',lambda db,d,st:
                        {'passed':False,'style_review':'rejected'})
    engine=make_engine('sqlite://')
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine,expire_on_commit=False)() as db:
        d=newsroom(db)
        with pytest.raises(ValueError,match='QC'):
            schedule.schedule_web_post(db,d,tomorrow_slot())
        assert d.scheduled_at is None
        monkeypatch.setattr(schedule,'report_for_draft',lambda db,d,st:
                            {'passed':True,'style_review':'passed'})
        d.rights_reviewed=False;d.photo_license='CC BY'
        with pytest.raises(ValueError,match='hak penggunaan|lisensi|Cover HTTPS'):
            schedule.schedule_web_post(db,d,tomorrow_slot())
        assert d.scheduled_at is None


def test_only_wib_publication_slots_allowed(monkeypatch):
    monkeypatch.setattr(schedule,'CONFIG',replace(schedule.CONFIG,live_publish=True))
    engine=make_engine('sqlite://')
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine,expire_on_commit=False)() as db:
        d=newsroom(db)
        with pytest.raises(ValueError,match='06.00'):
            schedule.schedule_web_post(db,d,tomorrow_slot(10))
        assert d.status=='pending_approval'


def test_content_studio_uses_actual_cover_not_html_overlay():
    from pathlib import Path
    html=(Path(__file__).resolve().parents[1]/'utbot'/'planner.html').read_text()
    assert 'id="finalCover"' in html
    assert 'id="badge"' not in html
    assert 'id="coverText"' not in html
    assert html.index('<section class="editor">') < html.index('class="calendar-bar"')
    assert 'Jadwalkan Otomatis' in html


def test_full_auto_generates_real_schedule_without_owner_data_entry(monkeypatch):
    """New rights-safe content after activation is scheduled and shown on calendar."""
    from utbot import automation_mode
    monkeypatch.setattr(automation_mode,'CONFIG',
                        replace(automation_mode.CONFIG,live_publish=True,photo_music_mode='manual'))
    monkeypatch.setattr(automation_mode,'photo_auto_safe',lambda d: True)
    monkeypatch.setattr('utbot.quality_control.report_for_draft',
                        lambda db,d,st:{'passed':True,'style_review':'passed'})
    engine=make_engine('sqlite://')
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine,expire_on_commit=False)() as db:
        automation_mode.set_mode(db,automation_mode.FULL_AUTO,'owner')
        d=newsroom(db)
        result=automation_mode.auto_approve_ready(db)
        assert d.id in result['approved'],result
        assert d.status=='approved'
        assert schedule.explicitly_auto_photo(db,d)
        queue=schedule_approved(db,daily_limit=3)
        assert d.scheduled_at is not None
        assert queue[0][0]==d.id
        assert d.scheduled_at.astimezone(WIB).hour in (6,12,18)
