"""Scheduled newsroom delivery is automatic and robust to Telegram failures."""
from sqlalchemy.orm import sessionmaker
from utbot.models import Base,make_engine,Story,Draft,Audit
from utbot.runner import deliver_pending_previews
from utbot.research import fingerprint


def seed():
    engine=make_engine('sqlite://')
    Base.metadata.create_all(engine)
    db=sessionmaker(bind=engine,expire_on_commit=False)()
    url='https://science.nasa.gov/test-delivery/'
    story=Story(fingerprint=fingerprint(url),title='NASA story',source_url=url,
                source_name='NASA',topic='astronomy')
    db.add(story);db.flush()
    draft=Draft(story_id=story.id,status='pending_approval',
                publish_state='unpublished',highlight='A live science discovery',
                caption='A caption.',hashtags=['#NASA'])
    db.add(draft);db.commit()
    return db,draft


def test_pending_auto_delivery_idempotent(monkeypatch):
    from utbot import runner
    db,draft=seed()
    calls=[]
    monkeypatch.setattr(runner,'send_preview',lambda *args:calls.append(1))
    try:
        first=deliver_pending_previews(db,object(),123)
        assert first['sent']==[draft.id]
        assert first['failed']==[]
        assert deliver_pending_previews(db,object(),123)['sent']==[]
        assert calls==[1]
        assert db.query(Audit).filter_by(event='telegram_preview_delivered').count()==1
    finally:db.close()


def test_failed_telegram_delivery_remains_retryable(monkeypatch):
    from utbot import runner
    db,draft=seed()
    calls=[]
    def fail(*args):
        calls.append(1)
        if len(calls)==1:raise RuntimeError('Telegram unavailable')
    monkeypatch.setattr(runner,'send_preview',fail)
    try:
        first=deliver_pending_previews(db,object(),123)
        assert first['failed'][0]['draft_id']==draft.id
        assert db.query(Audit).filter_by(event='telegram_preview_delivered').count()==0
        second=deliver_pending_previews(db,object(),123)
        assert second['sent']==[draft.id]
        assert calls==[1,1]
    finally:db.close()
