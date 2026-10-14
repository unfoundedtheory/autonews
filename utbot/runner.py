"""Single-instance worker: discovers candidates, prepares drafts, queues and publishes.

Use one worker replica, PostgreSQL, and persistent or cloud-hosted rendered media for production.
This service never enables live Instagram publishing; ENABLE_LIVE_PUBLISH remains the gate.
"""
import logging
import time
from datetime import datetime, timezone, timedelta
from .models import Session, init_db, Story, TelegramUpdateReceipt
from .research import discover
from sqlalchemy import delete
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

def do_prepare():
    bot = TelegramClient(CONFIG.telegram_token) if CONFIG.telegram_token and CONFIG.chat_id else None
    with Session() as db:
        def notify(d):
            if bot:
                send_preview(bot, CONFIG.chat_id, d, db.get(Story, d.story_id))
        from .stock_flow import stock_to_prepare
        quota = stock_to_prepare(db)
        if quota <= 0:
            log.info('draft stock target reached; skipping additional AI calls')
            return []
        result = prepare_batch(db, limit=quota, notifier=notify)
        log.info('prepared=%s', result)
        return result

def do_reschedule():
    with Session() as db:
        from .stock_flow import auto_approve_overdue
        auto_approve_overdue(db)
        result = schedule_approved(db, daily_limit=CONFIG.daily_limit)
        db.commit()
        return result

def do_maintenance():
    """Hourly read-only editorial eligibility and early music-kit delivery.

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
