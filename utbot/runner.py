"""Single-instance worker: discovers candidates, prepares drafts, queues and publishes.

Use one worker replica, PostgreSQL, and persistent or cloud-hosted rendered media for production.
This service never enables live Instagram publishing; ENABLE_LIVE_PUBLISH remains the gate.
"""
import logging
import time
from datetime import datetime, timezone, timedelta
from .models import Session, init_db, Story, Draft, Audit, TelegramUpdateReceipt
from .research import discover
from sqlalchemy import delete, select, func
from .pipeline import prepare_batch
from .telegram import TelegramClient, send_preview
from .scheduler import schedule_approved, WIB
from .config import CONFIG

log = logging.getLogger(__name__)

def do_discover():
    with Session() as db:
        from .research import evergreen_sources
        result=list(discover(db))
        if not any(int(x.get('inserted',0)) for x in result):
            result.extend(discover(db,sources=evergreen_sources()))
        db.execute(delete(TelegramUpdateReceipt).where(
            TelegramUpdateReceipt.received_at < datetime.now(timezone.utc)-timedelta(days=30)))
        db.commit()
        log.info('discovery=%s', result)
        return result

def deliver_pending_previews(db, bot, chat_id, limit=12):
    """Recover unacknowledged Telegram previews, even when stock is already full.

    A successful Telegram delivery is audited by draft version. Failures are
    kept eligible for the next scheduled run and never counted as delivered.
    """
    if not bot or not chat_id:
        return {'sent': [], 'failed': [], 'blocked': 'Telegram destination not configured'}
    from .automation_mode import current_mode, MANUAL_POST, deliver_manual_post_preview, manual_post_ready
    manual = current_mode(db)[0] == MANUAL_POST
    candidates=db.execute(select(Draft).where(
        Draft.status=='pending_approval', Draft.publish_state=='unpublished'
    ).order_by(Draft.created_at.desc(),Draft.id.desc()).limit(limit)).scalars().all()
    sent, failed=[],[]
    for draft in candidates:
        prior=db.execute(select(Audit.detail).where(
            Audit.draft_id==draft.id, Audit.event=='telegram_preview_delivered'
        )).scalars().all()
        if manual_post_ready(db,draft):
            continue
        if any((record or {}).get('version')==draft.version for record in prior) and not manual:
            continue
        try:
            if manual:
                deliver_manual_post_preview(db,draft,bot,chat_id)
            else:
                send_preview(bot,chat_id,draft,db.get(Story,draft.story_id))
            db.add(Audit(draft_id=draft.id,event='telegram_preview_delivered',
                         actor='worker',detail={'version':draft.version}))
            db.commit()
            sent.append(draft.id)
        except Exception as exc:
            db.rollback()
            log.warning('Pending preview delivery failed for %s: %s',
                        draft.id, type(exc).__name__)
            failed.append({'draft_id':draft.id,'error_type':type(exc).__name__})
    return {'sent':sent,'failed':failed}


def recover_missing_covers(db, *, limit=3):
    """Retry official-article covers for pending drafts after transient image outages.

    Do not approve photo rights or silently substitute unrelated images. A
    six-hour backoff prevents provider hammering on genuinely unsuitable pages.
    """
    from .cover_recovery import recover_article_cover
    candidates=db.execute(select(Draft).where(
        Draft.status=='pending_approval',
        Draft.publish_state=='unpublished',
        Draft.image_url.is_(None),
        Draft.source_image_url.is_(None),
    ).order_by(Draft.created_at.desc()).limit(24)).scalars().all()
    recovered=[]
    cutoff=datetime.now(timezone.utc)-timedelta(hours=6)
    for draft in candidates:
        previous=db.execute(select(Audit.id).where(
            Audit.draft_id==draft.id,
            Audit.event=='cover_recovery_attempted',
            Audit.created_at>=cutoff).limit(1)).first()
        if previous:
            continue
        story=db.get(Story,draft.story_id)
        if not story:
            continue
        db.add(Audit(draft_id=draft.id,event='cover_recovery_attempted',
                     actor='worker',detail={'version':draft.version}))
        db.commit()
        try:
            recover_article_cover(db,draft,story,actor='worker:cover_recovery')
            db.commit()
            recovered.append(draft.id)
        except Exception as exc:
            db.rollback()
            log.warning('Cover recovery failed %s: %s',draft.id,type(exc).__name__)
        if len(recovered)>=limit:
            break
    return recovered


def do_prepare():
    bot = TelegramClient(CONFIG.telegram_token) if CONFIG.telegram_token and CONFIG.chat_id else None
    with Session() as db:
        from .automation_mode import auto_approve_ready
        recovered_covers=recover_missing_covers(db)
        # Send already-prepared drafts first: generating new AI text does not
        # help if the editor never received the existing pending news.
        delivery=deliver_pending_previews(db,bot,CONFIG.chat_id)
        from .stock_flow import stock_to_prepare
        # Four creation slots are a daily goal, not a cap on old approvals.
        # A full backlog must never silently stop all future news production.
        # Count all drafts created today, regardless of approval/posting state,
        # so repeated cron invocations cannot exceed the daily target.
        now_wib=datetime.now(timezone.utc).astimezone(WIB)
        day_start=now_wib.replace(hour=0,minute=0,second=0,microsecond=0)
        next_day=day_start+timedelta(days=1)
        already=db.execute(select(func.count(Draft.id)).where(
            Draft.created_at>=day_start.astimezone(timezone.utc),
            Draft.created_at<next_day.astimezone(timezone.utc)
        )).scalar_one()
        remaining=max(0,4-already)
        quota=min(1,remaining)
        if quota <= 0:
            automatic=auto_approve_ready(db)
            if automatic['approved']:
                schedule_approved(db,daily_limit=CONFIG.daily_limit)
                db.commit()
            log.info('draft stock target reached; recovery=%s',delivery)
            return {'prepared':[], 'delivery':delivery,'automatic':automatic,'recovered_covers':recovered_covers,'daily_created':already,'daily_target':4,'skip_reason':'daily_target_met'}
        # prepare_batch commits new drafts before notifying. The recovery pass
        # owns Telegram delivery and writes a durable delivery marker.
        result=prepare_batch(db, limit=quota, notifier=None)
        automatic=auto_approve_ready(db)
        if automatic['approved']:
            schedule_approved(db,daily_limit=CONFIG.daily_limit)
            db.commit()
        latest=deliver_pending_previews(db,bot,CONFIG.chat_id)
        log.info('prepared=%s delivery=%s', result,latest)
        return {'prepared':result, 'delivery':{
            'sent':delivery['sent']+latest['sent'],
            'failed':delivery['failed']+latest['failed']},'automatic':automatic,'recovered_covers':recovered_covers,'daily_created':already+sum(1 for row in result if row.get('status')=='prepared'),'daily_target':4}

def do_reschedule():
    with Session() as db:
        from .stock_flow import auto_approve_overdue
        auto_approve_overdue(db)
        from .automation_mode import auto_approve_ready
        auto_approve_ready(db)
        result = schedule_approved(db, daily_limit=CONFIG.daily_limit)
        db.commit()
        return result

def do_maintenance():
    """Scheduled editorial eligibility checks and early music-kit delivery.

    May *approve* QC-passed drafts after 24 hours, but NEVER publishes here.
    """
    from .stock_flow import auto_approve_overdue, dispatch_approved_kits
    bot = TelegramClient(CONFIG.telegram_token) if CONFIG.telegram_token else None
    with Session() as db:
        decisions = auto_approve_overdue(db)
        kits = dispatch_approved_kits(db, bot, CONFIG.chat_id)
        return {'timeout':decisions, 'music_kits':kits}

def do_publish():
    # Reuse the exact publication gate, idempotency and uncertainty handling of the API.
    from .web import publish_job
    with Session() as db:
        return publish_job(db=db)

def run_cycle(*, include_discovery=False):
    if include_discovery:
        do_discover()
    do_prepare()
    do_reschedule()
    return do_publish()

def loop(sleep=time.sleep, clock=None):
    """Worker 24/7; job frequency controlled by WIB time and loop-local de-duplication.

    On process restart discovery and preparation run once, safely deduped in the DB.
    Publishing is retried at most every five minutes; uncertain posts never retried.
    """
    init_db()
    clock = clock or (lambda: datetime.now(timezone.utc))
    last = {}
    while True:
        now = clock().astimezone(WIB)
        # Periodic discovery/preparation on each even local hour.
        hour_key = (now.date().isoformat(), now.hour)
        if now.hour % 2 == 0 and last.get('research') != hour_key:
            try:
                do_discover(); do_prepare()
            except Exception:
                log.exception('Research batch failed')
            last['research'] = hour_key
        # Rebuild slots once every five minutes, then publish due approved stories.
        window = (now.date().isoformat(), now.hour, now.minute // 5)
        if last.get('queue') != window:
            try:
                do_reschedule(); log.info('publish=%s', do_publish())
            except Exception:
                log.exception('Queue/publish batch failed')
            last['queue'] = window
        sleep(30)

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Unfounded Theory editorial worker')
    parser.add_argument('command', choices=['loop', 'discover', 'prepare', 'reschedule', 'publish', 'cycle'])
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    init_db()
    methods={'discover':do_discover,'prepare':do_prepare,'reschedule':do_reschedule,
             'publish':do_publish,'cycle':lambda:run_cycle(include_discovery=True)}
    if args.command == 'loop': loop()
    else: print(methods[args.command]())

if __name__ == '__main__':
    main()
