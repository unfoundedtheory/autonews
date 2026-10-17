"""Failed candidates may be retried later without starving the rest of the queue."""
from datetime import datetime, timezone
from sqlalchemy.orm import sessionmaker
from utbot.models import Base, make_engine, Story, Draft, Audit
from utbot.research import fingerprint
from utbot import pipeline


def test_failed_candidate_rotates_and_next_one_prepares(monkeypatch):
    engine=make_engine('sqlite://')
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine,expire_on_commit=False)() as db:
        stories=[]
        for i in range(3):
            url=f'https://science.nasa.gov/rotating-{i}'
            st=Story(fingerprint=fingerprint(url),title=f'Observasi {i}',
                     source_url=url,source_name='NASA',topic='astronomy',
                     verification_status='needs_fact_check',
                     published_at=datetime(2026,10,17-i,tzinfo=timezone.utc))
            db.add(st);db.flush();stories.append(st)
        db.commit()
        attempts=[]
        def prepare(db,st):
            attempts.append(st.id)
            if st.id==stories[0].id:
                raise ValueError('Reviewer still needs a rewrite')
            draft=Draft(story_id=st.id,highlight='Temuan sains',
                        caption='Caption',hashtags=['#Sains'],status='pending_approval')
            db.add(draft);db.flush()
            return draft
        monkeypatch.setattr(pipeline,'prepare_story',prepare)
        first=pipeline.prepare_batch(db,limit=1)
        assert first[0]['status']=='prepared'
        assert attempts==[stories[0].id,stories[1].id]
        assert db.query(Audit).filter_by(event='candidate_prepare_failed').count()==1
        attempts.clear()
        second=pipeline.prepare_batch(db,limit=1)
        assert second[0]['status']=='prepared'
        assert attempts==[stories[2].id]
