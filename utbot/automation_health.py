"""Persistent, non-secret cron audit for the operator's Telegram status screen.

Use the existing private Audit table rather than creating a public table.
A heartbeat confirms the HTTP cron handler ran, not that Telegram or Instagram
delivery was accepted by remote platforms.
"""
from datetime import datetime, timezone, timedelta
import logging
from sqlalchemy import select, delete
from .models import Audit, Session
from .scheduler import WIB

log = logging.getLogger(__name__)
SYSTEM_DRAFT_ID = 'system-automation'
HEARTBEAT_EVENT = 'automation_heartbeat'
JOBS = ('discover','prepare','prepare_afternoon','tick_morning',
        'tick_noon','tick_evening','maintenance')

def record_heartbeat(job, outcome, error_type=None):
    if job not in JOBS or outcome not in ('success','failed'):
        raise ValueError('Unknown automation job/outcome')
    with Session() as db:
        db.add(Audit(draft_id=SYSTEM_DRAFT_ID,event=HEARTBEAT_EVENT,
                     actor='cron:'+job,
                     detail={'outcome':outcome,
                             'error_type':error_type if outcome=='failed' else None}))
        cutoff=datetime.now(timezone.utc)-timedelta(days=30)
        db.execute(delete(Audit).where(
            Audit.event==HEARTBEAT_EVENT,Audit.draft_id==SYSTEM_DRAFT_ID,
            Audit.created_at<cutoff))
        db.commit()

def tracked_cron(job, operation):
    """Log completed outcomes safely; never store returned stories or secrets."""
    try:
        result=operation()
    except Exception as exc:
        try:
            record_heartbeat(job,'failed',type(exc).__name__)
        except Exception:
            log.exception('Unable to record cron failure')
        raise
    record_heartbeat(job,'success')
    return result

def automation_status(db, *, now=None):
    """Concise Telegram summary; does not expose credentials or draft contents."""
    now=now or datetime.now(timezone.utc)
    rows=db.execute(select(Audit).where(
        Audit.event==HEARTBEAT_EVENT,
        Audit.draft_id==SYSTEM_DRAFT_ID).order_by(Audit.created_at.desc()).limit(250)
    ).scalars().all()
    latest={}
    for row in rows:
        job=str(row.actor).removeprefix('cron:')
        if job in JOBS and job not in latest:
            latest[job]=row
    labels={
        'discover':'Cari berita',
        'prepare':'Siapkan draf pagi',
        'prepare_afternoon':'Siapkan draf sore',
        'tick_morning':'Slot 06.00 WIB',
        'tick_noon':'Slot 12.00 WIB',
        'tick_evening':'Slot 18.00 WIB',
        'maintenance':'Pemeliharaan',
    }
    lines=['🤖 AUTOMATION (30 hari terakhir)']
    for job in JOBS:
        row=latest.get(job)
        if not row:
            lines.append('▫️ '+labels[job]+': belum ada heartbeat')
            continue
        at=row.created_at.replace(tzinfo=timezone.utc) if row.created_at.tzinfo is None else row.created_at
        status=(row.detail or {}).get('outcome')
        age=now.astimezone(timezone.utc)-at.astimezone(timezone.utc)
        icon='✅' if status=='success' else '❌'
        if status=='success' and age>timedelta(hours=27):icon='⚠️'
        stamp=at.astimezone(WIB).strftime('%d/%m %H:%M')
        lines.append(f'{icon} {labels[job]}: {stamp} WIB'+(
            ' (stale)' if icon=='⚠️' else ''))
    lines.append('Heartbeat hanya bukti job selesai; bukan konfirmasi publikasi Instagram.')
    return '\n'.join(lines)
