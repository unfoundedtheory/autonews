"""Automatic preview recovery on cron, without requiring Generate button."""
from sqlalchemy.orm import sessionmaker
from utbot.models import Base,make_engine,Story,Draft,Audit
from utbot.runner import deliver_pending_previews
from utbot.research import fingerprint


def test_auto_delivery_records_success_and_is_idempotent(monkeypatch):
    engine=make_engine('sqlite://')
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine,expire_on_commit=False)() as db:
        url='https://science.nasa.gov/test-auto-preview'
        st=Story(fingerprint=fingerprint(url),title='Test science',source_url=url,
                 source_name='NASA',topic='astronomy')
        db.add(st);db.flush()
        d=Draft(story_id=st.id,highlight='Observasi Bintang',
                caption='Hasil observasi bintang.',hashtags=['#Sains'],
                status='pending_approval',image_url='https://example.com/cover.jpg')
        db.add(d);db.commit()
        sent=[]
        class Bot: pass
        monkeypatch.setattr('utbot.runner.send_preview',
                            lambda bot,chat,draft,story:sent.append(draft.id))
        assert deliver_pending_previews(db,Bot(),123)['sent']==[d.id]
        assert deliver_pending_previews(db,Bot(),123)['sent']==[]
        assert sent==[d.id]
        d.version+=1;db.commit()
        assert deliver_pending_previews(db,Bot(),123)['sent']==[d.id]
        assert sent==[d.id,d.id]


def test_failed_delivery_retries_without_false_success(monkeypatch):
    engine=make_engine('sqlite://')
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine,expire_on_commit=False)() as db:
        url='https://science.nasa.gov/test-preview-retry'
        st=Story(fingerprint=fingerprint(url),title='Test science',source_url=url,
                 source_name='NASA',topic='astronomy')
        db.add(st);db.flush()
        d=Draft(story_id=st.id,highlight='Observasi Bintang',
                caption='Hasil observasi bintang.',hashtags=['#Sains'],
                status='pending_approval')
        db.add(d);db.commit()
        class Bot: pass
        def fail(*args):raise RuntimeError('Telegram unavailable')
        monkeypatch.setattr('utbot.runner.send_preview',fail)
        assert len(deliver_pending_previews(db,Bot(),123)['failed'])==1
        assert db.query(Audit).filter_by(event='telegram_preview_sent').count()==0
        monkeypatch.setattr('utbot.runner.send_preview',lambda *args:None)
        assert deliver_pending_previews(db,Bot(),123)['sent']==[d.id]
