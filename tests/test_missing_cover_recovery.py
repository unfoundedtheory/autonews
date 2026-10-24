"""Regression tests for automatic missing-cover recovery."""
import httpx
from sqlalchemy.orm import sessionmaker
from utbot.models import Base, make_engine, Story, Draft, Audit
from utbot import runner, media

def test_commons_identifies_bot():
    calls=[]
    def handle(req):
        calls.append(req)
        return httpx.Response(403,json={'error':'forbidden'})
    try:
        media.find_photos('telescope',transport=httpx.MockTransport(handle))
        assert False
    except httpx.HTTPStatusError as exc:
        assert exc.response.status_code==403
    assert 'unfoundedtheory@gmail.com' in calls[0].headers['user-agent']
    assert calls[0].headers['accept']=='application/json'

def test_pending_cover_recovered_once(monkeypatch):
    engine=make_engine('sqlite://')
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine,expire_on_commit=False)() as db:
        story=Story(fingerprint='retry',title='NASA Telescope',source_url='https://science.nasa.gov/test/',source_name='NASA')
        db.add(story);db.flush()
        draft=Draft(story_id=story.id,highlight='Scientific Finding',caption='Test',hashtags=[])
        db.add(draft);db.commit()
        calls=[]
        def recover(db,d,s,actor):
            calls.append(d.id)
            d.source_image_url='https://example.org/source.jpg'
            d.image_url='https://example.org/cover.jpg'
        monkeypatch.setattr('utbot.cover_recovery.recover_article_cover',recover)
        assert runner.recover_missing_covers(db)==[draft.id]
        assert draft.image_url and not draft.rights_reviewed
        assert runner.recover_missing_covers(db)==[]
        assert calls==[draft.id]

def test_failed_cover_recovery_has_backoff(monkeypatch):
    engine=make_engine('sqlite://')
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine,expire_on_commit=False)() as db:
        story=Story(fingerprint='retry-fail',title='NASA',source_url='https://science.nasa.gov/test/',source_name='NASA')
        db.add(story);db.flush()
        d=Draft(story_id=story.id,highlight='Finding',caption='Test',hashtags=[])
        db.add(d);db.commit()
        calls=[]
        def fail(*a,**k):
            calls.append(1)
            raise ValueError('No matched photo')
        monkeypatch.setattr('utbot.cover_recovery.recover_article_cover',fail)
        assert runner.recover_missing_covers(db)==[]
        assert runner.recover_missing_covers(db)==[]
        assert len(calls)==1
        assert db.query(Audit).filter_by(draft_id=d.id,event='cover_recovery_attempted').count()==1
