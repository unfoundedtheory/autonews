from datetime import datetime,timezone,timedelta
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
from utbot.models import Base,make_engine,Story,Draft
from utbot.editorial import approve,revise,lint
from utbot.scheduler import schedule_approved,WIB
from utbot.research import fingerprint,parse_items
import pytest

@pytest.fixture
def db():
    engine=make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine,expire_on_commit=False)() as ses:
        yield ses

def factory(db,n=1):
    out=[]
    for i in range(n):
        url=f"https://www.nasa.gov/test/story{i}"
        story=Story(fingerprint=fingerprint(url),title=f"NASA story {i}",source_url=url,source_name="NASA",topic="astronomy",verification_status="verified",evidence=[{"claim":"NASA says this","url":url,"evidence_checked":True}])
        db.add(story);db.flush()
        draft=Draft(story_id=story.id,highlight="Fisikawan Temukan Sinyal Aneh Dalam Pencarian Partikel Dark Matter",caption="Akhirnya beberapa ilmuwan menyaksikan sesuatu yang aneh.\n\nNASA menjelaskan temuan ini dalam laporan terbaru.\n\nNamun, pengamatan itu belum merupakan bukti akhir.\n\nApa lagi yang akan diungkap oleh pengamatan berikutnya?",hashtags=["#Astronomi","#NASA","#Sains","#AlamSemesta","#UnfoundedTheory"],image_url="https://example.org/photo.jpg",rights_reviewed=True,photo_license="NASA public domain",image_credit="NASA")
        db.add(draft);db.flush();out.append(draft)
    db.commit()
    return out

def test_revisions_revoke_approval(db):
    d=factory(db)[0]
    approve(db,d,"42");db.commit()
    assert d.status=="approved" and d.approved_version==1
    revise(db,d,"highlight","NASA Mengamati Fenomena Aneh Dari Wilayah Antariksa Yang Jauh","42")
    assert d.status=="pending_approval" and d.approved_version is None and d.version==2
    assert d.scheduled_at is None

def test_approval_without_separate_photo_confirm(db):
    d=factory(db)[0]
    d.rights_reviewed=False
    approve(db,d,"42")
    assert d.status=="approved"
    assert d.rights_reviewed is True


def test_facts_and_final_cover_remain_required(db):
    d=factory(db)[0]
    d.image_url=None
    with pytest.raises(ValueError,match="Cover final"):approve(db,d,"42")
    d.image_url="https://example.org/photo.jpg"
    st=db.get(Story,d.story_id)
    st.verification_status="needs_fact_check"
    with pytest.raises(ValueError,match="verifikasi"):approve(db,d,"42")


def test_backlog_max_two_per_day_with_three_slots(db):
    ds=factory(db,5)
    for d in ds:approve(db,d,"42")
    # 2026-10-10 00:00 WIB, before all three slots
    now=datetime(2026,10,9,17,0,tzinfo=timezone.utc)
    schedule_approved(db,now=now,daily_limit=2)
    days=[d.scheduled_at.astimezone(WIB).date().isoformat() for d in ds]
    hours=[d.scheduled_at.astimezone(WIB).hour for d in ds]
    assert days==["2026-10-10","2026-10-10","2026-10-11","2026-10-11","2026-10-12"]
    assert hours==[6,12,6,12,6]

def test_evening_fallback_slot(db):
    ds=factory(db,2)
    for d in ds:approve(db,d,"42")
    # 14:00 WIB: only 18:00 remains today
    now=datetime(2026,10,10,7,0,tzinfo=timezone.utc)
    schedule_approved(db,now=now,daily_limit=2)
    assert ds[0].scheduled_at.astimezone(WIB).hour==18
    assert ds[1].scheduled_at.astimezone(WIB).day==11

def test_editorial_rules():
    issues=lint("NASA BERITA KAPITAL", "Pendek tanpa bagian lain.",["#A"])
    assert "highlight_not_title_case" in issues
    assert "hashtag_format" in issues

def test_url_dedup():
    assert fingerprint("https://www.nasa.gov/test?utm_source=ig") == fingerprint("https://www.nasa.gov/test/")

def test_database_rejects_second_draft_for_same_story(db):
    first=factory(db)[0]
    db.add(Draft(story_id=first.story_id,highlight=first.highlight,caption=first.caption,
                 hashtags=first.hashtags,rights_reviewed=True))
    with pytest.raises(IntegrityError):db.flush()

def test_rss_parse():
    doc=b'<rss><channel><item><title>Space Event</title><link>https://www.nasa.gov/2026/test</link><pubDate>Sat, 10 Oct 2026 10:00:00 GMT</pubDate></item></channel></rss>'
    assert len(parse_items(doc))==1


def test_published_today_consumes_daily_quota(db):
    ds=factory(db,4)
    for d in ds:approve(db,d,"42")
    now=datetime(2026,10,9,17,0,tzinfo=timezone.utc)
    schedule_approved(db,now=now,daily_limit=2)
    ds[0].status="published";ds[0].publish_state="published"
    ds[1].status="published";ds[1].publish_state="published"
    schedule_approved(db,now=now+timedelta(hours=7),daily_limit=2)
    assert all(d.scheduled_at.astimezone(WIB).day==11 for d in ds[2:])

def test_expired_story_is_not_due(db):
    from utbot.scheduler import due
    d=factory(db)[0]
    approve(db,d,"42")
    d.scheduled_at=datetime(2026,10,10,5,0,tzinfo=timezone.utc)
    d.expires_at=datetime(2026,10,10,5,30,tzinfo=timezone.utc)
    assert not due(db,datetime(2026,10,10,6,0,tzinfo=timezone.utc))
    assert d.status=="expired_needs_review"


def test_three_daily_publishing_slots_preserve_original_times(db):
    from utbot.scheduler import SLOTS
    from utbot.config import Config
    assert SLOTS == (6, 12, 18)
    assert Config().daily_limit == 3
    ds=factory(db,5)
    for d in ds: approve(db,d,'42')
    now=datetime(2026,10,9,17,0,tzinfo=timezone.utc)
    schedule_approved(db,now=now,daily_limit=3)
    hours=[d.scheduled_at.astimezone(WIB).hour for d in ds]
    days=[d.scheduled_at.astimezone(WIB).date().isoformat() for d in ds]
    assert hours == [6,12,18,6,12]
    assert days == ['2026-10-10']*3+['2026-10-11']*2


def test_existing_approved_slots_never_roll_forward_when_cron_runs_late(db):
    """Missed 06/12/18 posts stay overdue, not silently moved to tomorrow."""
    from utbot.scheduler import due
    drafts=factory(db,5)
    for draft in drafts:approve(db,draft,"42")
    first=datetime(2026,10,19,17,0,tzinfo=timezone.utc)  # 20 Oct 00 WIB
    initial=schedule_approved(db,now=first,daily_limit=3)
    db.commit()
    original={item:schedule for item,schedule in initial}
    assert [d.scheduled_at.astimezone(WIB).day for d in drafts]==[20,20,20,21,21]
    after_evening=datetime(2026,10,20,13,0,tzinfo=timezone.utc) # 20 Oct 20 WIB
    for offset in (0,1,8,25,49):
        schedule_approved(db,now=after_evening+timedelta(hours=offset),daily_limit=3)
        db.commit()
        assert {d.id:d.scheduled_at for d in drafts}==original
    overdue=due(db,after_evening)
    assert {d.id for d in overdue}=={d.id for d in drafts[:3]}


def test_new_approvals_do_not_reassign_existing_approved_and_overdue_posts(db):
    drafts=factory(db,4)
    for draft in drafts[:3]: approve(db,draft,"42")
    initial=datetime(2026,10,19,17,0,tzinfo=timezone.utc)
    schedule_approved(db,now=initial,daily_limit=3)
    original=[draft.scheduled_at for draft in drafts[:3]]
    approve(db,drafts[3],"42")
    morning=datetime(2026,10,19,23,30,tzinfo=timezone.utc)  # 20 Oct 06:30 WIB
    schedule_approved(db,now=morning,daily_limit=3)
    assert [draft.scheduled_at for draft in drafts[:3]]==original
    assert drafts[3].scheduled_at.astimezone(WIB).date().isoformat()=='2026-10-21'
    assert drafts[3].scheduled_at.astimezone(WIB).hour==6


def test_web_pinned_and_manual_approval_slots_both_remain_immutable(db):
    from utbot.models import Audit
    ds=factory(db,2)
    for draft in ds:approve(db,draft,"42")
    pinned=datetime(2026,10,21,5,0,tzinfo=timezone.utc) # 21 Oct 12 WIB
    ds[0].scheduled_at=pinned
    db.add(Audit(draft_id=ds[0].id,event='photo_only_approved',
                 actor='content_studio',detail={'version':ds[0].version,'source':'content_studio'}))
    db.add(Audit(draft_id=ds[0].id,event='content_plan_changed',
                 actor='content_studio',detail={'version':ds[0].version,
                 'planned_at':pinned.isoformat(),'auto_publish':True}))
    other=datetime(2026,10,19,23,0,tzinfo=timezone.utc)
    ds[1].scheduled_at=other
    db.commit()
    schedule_approved(db,now=datetime(2026,10,21,6,0,tzinfo=timezone.utc),daily_limit=3)
    assert ds[0].scheduled_at==pinned
    assert ds[1].scheduled_at==other
