from sqlalchemy.orm import sessionmaker
from utbot.models import Base,make_engine,Story,Draft
from utbot.publication_guard import image_identity,reused_photo,auto_visual_safe

def test_source_photo_identity_ignores_tracking_query():
    assert image_identity("https://upload.wikimedia.org/x.jpg?utm_source=one") == image_identity("https://upload.wikimedia.org/x.jpg?utm_source=two")

def test_removed_photo_cannot_auto_approve_other_draft():
    engine=make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        one=Story(fingerprint="one",title="NASA Sound",source_url="https://www.nasa.gov/one",source_name="NASA")
        two=Story(fingerprint="two",title="NASA Acoustics",source_url="https://www.nasa.gov/two",source_name="NASA")
        db.add_all([one,two]);db.flush()
        removed=Draft(story_id=one.id,highlight="old",caption="old",hashtags=[],
            source_image_url="https://upload.wikimedia.org/a.jpg?utm_source=old",
            status="removed_by_owner",publish_state="published")
        new=Draft(story_id=two.id,highlight="new",caption="new",hashtags=[],
            source_image_url="https://upload.wikimedia.org/a.jpg?utm_source=new",
            image_credit="NASA Mission Control",media_page_url="https://commons.wikimedia.org/a")
        db.add_all([removed,new]);db.flush()
        assert reused_photo(db,new).id==removed.id
        assert auto_visual_safe(db,new,two)==(False,"previously_used_photo")

def test_generic_nasa_credit_does_not_verify_technical_visual():
    engine=make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        story=Story(fingerprint="generic",title="NASA Jet Engine Acoustic Instrument",
            source_url="https://www.nasa.gov/jet",source_name="NASA")
        db.add(story);db.flush()
        d=Draft(story_id=story.id,highlight="headline",caption="body",hashtags=[],
            source_image_url="https://upload.wikimedia.org/misson_control.jpg",
            image_credit="NASA Johnson Houston Mission Control",
            media_page_url="https://commons.wikimedia.org/wiki/File:mission_control.jpg")
        db.add(d);db.flush()
        assert auto_visual_safe(db,d,story)==(False,"photo_subject_unverified")
