from datetime import datetime,timedelta,time,timezone
from zoneinfo import ZoneInfo
from sqlalchemy import select,text
from .models import Draft,Audit

WIB=ZoneInfo("Asia/Jakarta")
SLOTS=(6,12,18)

def schedule_approved(db, now=None, daily_limit=2, horizon_days=90):
    """Rebuild *future* queue only. Slots are available at 06/12/18, daily max 2.

    Use a database transaction/advisory lock around this operation in production.
    """
    if not 1<=daily_limit<=3: raise ValueError("limit must be between 1 and 3")
    # Serialize queue rebuild across simultaneous worker and Telegram approval.
    if db.bind.dialect.name == 'postgresql':
        db.execute(text('SELECT pg_advisory_xact_lock(917540134)'))
    now=(now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    local=now.astimezone(WIB)
    ds=db.execute(select(Draft).where(Draft.status=="approved", Draft.approved_version==Draft.version, Draft.publish_state=="unpublished").order_by(Draft.approved_at,Draft.created_at,Draft.id)).scalars().all()
    occupied={} # daily quota, including already published/uncertain posts
    used_slots=set() # at most ONE post in a given slot
    locked=db.execute(select(Draft).where(Draft.scheduled_at.is_not(None), Draft.publish_state.in_(["published","publishing","uncertain","awaiting_container","manual_music_pending"]))).scalars().all()
    for p in locked:
        slot=p.scheduled_at.replace(tzinfo=timezone.utc) if p.scheduled_at.tzinfo is None else p.scheduled_at
        day=slot.astimezone(WIB).date()
        occupied[day]=occupied.get(day,0)+1
        used_slots.add(slot)
    for d in ds:
        d.scheduled_at=None
    candidates=[]
    for offset in range(horizon_days):
        day=local.date()+timedelta(days=offset)
        for hour in SLOTS:
            slot=datetime.combine(day,time(hour),WIB).astimezone(timezone.utc)
            if slot>now:
                candidates.append((day,slot))
    for d in ds:
        for day,slot in candidates:
            if occupied.get(day,0)>=daily_limit or slot in used_slots: continue
            if d.expires_at:
                expiry=d.expires_at.replace(tzinfo=timezone.utc) if d.expires_at.tzinfo is None else d.expires_at
                if expiry<=slot: continue
            d.scheduled_at=slot
            occupied[day]=occupied.get(day,0)+1
            used_slots.add(slot)
            break
        if d.scheduled_at is None:
            d.last_error="Belum ada slot sebelum kedaluwarsa (atau antrean terlalu panjang)"
    db.flush()
    return [(d.id, d.scheduled_at) for d in ds]


def due(db, now=None):
    now=now or datetime.now(timezone.utc)
    # SQLAlchemy SQLite naive timestamp normalization
    q=select(Draft).where(Draft.status=="approved",Draft.approved_version==Draft.version,Draft.publish_state.in_(["unpublished","awaiting_container"]),Draft.scheduled_at<=now).order_by(Draft.scheduled_at)
    rows=db.execute(q).scalars().all()
    valid=[]
    for d in rows:
        if d.expires_at:
            expiration=d.expires_at.replace(tzinfo=timezone.utc) if d.expires_at.tzinfo is None else d.expires_at
            if expiration<=now:
                d.status="expired_needs_review"
                d.scheduled_at=None
                continue
        valid.append(d)
    return valid
