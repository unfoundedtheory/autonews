"""Prove cron outcomes persist without exposing tokens or posting anywhere."""
from datetime import datetime,timezone,timedelta
from sqlalchemy.orm import sessionmaker
from utbot.models import Base,make_engine,Audit
from utbot import automation_health as monitor
from utbot import renderer

def test_automation_heartbeat_and_status(monkeypatch):
    engine=make_engine('sqlite://')
    Base.metadata.create_all(engine)
    sessions=sessionmaker(bind=engine,expire_on_commit=False)
    monkeypatch.setattr(monitor,'Session',sessions)
    assert monitor.tracked_cron('discover',lambda: {'discovery':[]})=={'discovery':[]}
    with sessions() as db:
        rows=db.query(Audit).filter(Audit.event==monitor.HEARTBEAT_EVENT).all()
        assert len(rows)==1
        assert rows[0].actor=='cron:discover'
        assert rows[0].detail=={'outcome':'success','error_type':None}
        status=monitor.automation_status(db)
        assert 'Cari berita' in status and '✅' in status
        assert 'belum ada heartbeat' in status

def test_failed_job_records_type_only_and_propagates(monkeypatch):
    engine=make_engine('sqlite://')
    Base.metadata.create_all(engine)
    sessions=sessionmaker(bind=engine,expire_on_commit=False)
    monkeypatch.setattr(monitor,'Session',sessions)
    def raises():
        raise RuntimeError('PRIVATE_KEY_should_never_appear')
    try:
        monitor.tracked_cron('tick_morning',raises)
    except RuntimeError:
        pass
    else:
        assert False,'Error should propagate to cron'
    with sessions() as db:
        row=db.query(Audit).filter(Audit.event==monitor.HEARTBEAT_EVENT).one()
        assert row.detail['outcome']=='failed'
        assert row.detail['error_type']=='RuntimeError'
        assert 'PRIVATE_KEY' not in str(row.detail)

def test_stale_success_is_visibly_flagged(monkeypatch):
    engine=make_engine('sqlite://')
    Base.metadata.create_all(engine)
    sessions=sessionmaker(bind=engine,expire_on_commit=False)
    with sessions() as db:
        db.add(Audit(draft_id=monitor.SYSTEM_DRAFT_ID,
                     event=monitor.HEARTBEAT_EVENT,actor='cron:maintenance',
                     detail={'outcome':'success','error_type':None},
                     created_at=datetime.now(timezone.utc)-timedelta(hours=28)))
        db.commit()
        assert '(stale)' in monitor.automation_status(db)

def test_reference_neon_is_exact_and_white_remains_opaque():
    assert renderer.GREEN=='#8FFF00'
    assert renderer.WHITE=='#FFFFFF'


def test_manual_mode_does_not_require_approval_or_publish(monkeypatch):
    from utbot.automation_mode import set_mode,current_mode,MANUAL_POST,manual_post_ready,deliver_manual_post_preview
    from utbot.models import Story,Draft
    engine=make_engine('sqlite://')
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine,expire_on_commit=False)() as db:
        set_mode(db,MANUAL_POST,'42')
        assert current_mode(db)[0]==MANUAL_POST
        story=Story(fingerprint='z'*64,title='NASA discovery',
                    source_url='https://science.nasa.gov/universe/',source_name='NASA')
        db.add(story);db.flush()
        draft=Draft(story_id=story.id,highlight='Scientific study uncovers new data',
                    caption='Data from a verified study.',hashtags=['#Science'],
                    image_url='https://example.org/cover.jpg')
        db.add(draft);db.commit()
        calls=[]
        import utbot.telegram as telegram
        monkeypatch.setattr(telegram,'send_preview',
                            lambda bot,chat,d,story,manual_post=False:
                            calls.append(manual_post))
        assert deliver_manual_post_preview(db,draft,object(),'chat') is True
        assert deliver_manual_post_preview(db,draft,object(),'chat') is False
        assert calls==[True]
        assert manual_post_ready(db,draft)
        assert draft.status=='pending_approval'
        assert draft.approved_version is None
        assert draft.scheduled_at is None
