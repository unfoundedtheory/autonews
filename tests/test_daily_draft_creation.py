"""Scheduled draft creation must not stop when old approvals fill the stock."""
from datetime import datetime,timezone
from types import SimpleNamespace
from sqlalchemy.orm import sessionmaker
from utbot.models import Base,make_engine,Story,Draft
from utbot import runner

def test_full_stock_still_creates_one_new_draft_per_slot(monkeypatch):
    engine=make_engine('sqlite://')
    Base.metadata.create_all(engine)
    db=sessionmaker(bind=engine,expire_on_commit=False)()
    for n in range(16):
        story=Story(fingerprint=str(n),title='Archive',source_url='https://nasa.gov/',source_name='NASA')
        db.add(story);db.flush()
        db.add(Draft(story_id=story.id,highlight='Archive',caption='Old',hashtags=[],
                     created_at=datetime(2026,10,20,tzinfo=timezone.utc)))
    db.commit()
    class SessionContext:
        def __enter__(self):return db
        def __exit__(self,*args):pass
    monkeypatch.setattr(runner,'Session',lambda:SessionContext())
    monkeypatch.setattr(runner,'TelegramClient',lambda *args:None)
    monkeypatch.setattr(runner,'recover_missing_covers',lambda *args,**kwargs:[])
    monkeypatch.setattr(runner,'deliver_pending_previews',
        lambda *args,**kwargs:{'sent':[],'failed':[]})
    monkeypatch.setattr('utbot.automation_mode.auto_approve_ready',
        lambda *args,**kwargs:{'approved':[]})
    called=[]
    monkeypatch.setattr(runner,'prepare_batch',lambda db,limit,notifier:
        called.append(limit) or [{'status':'prepared','draft_id':'new'}])
    out=runner.do_prepare()
    assert called==[1]
    assert out['daily_target']==4
    assert out['prepared'][0]['status']=='prepared'
    db.close()
