"""Regression checks for on-demand discovery and Telegram replay protection."""
from datetime import datetime, timezone
from sqlalchemy.orm import sessionmaker
from utbot.models import Base, make_engine, TelegramUpdateReceipt
from utbot.research import parse_items, canonicalize
from utbot import web, research


def db_session():
    engine=make_engine('sqlite://')
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def test_apod_html_urls_preserve_extension_and_atom_is_parsed():
    url='https://apod.nasa.gov/apod/ap261013.html'
    assert canonicalize(url)==url
    feed=b'''<feed xmlns="http://www.w3.org/2005/Atom">
      <entry><title>New Moon Image</title><link rel="alternate" href="https://science.nasa.gov/new-moon/"/>
      <updated>2026-10-13T09:00:00Z</updated></entry></feed>'''
    items=parse_items(feed)
    assert len(items)==1 and items[0]['title']=='New Moon Image'
    assert items[0]['pub']==datetime(2026,10,13,9,0,tzinfo=timezone.utc)


def test_empty_queue_discovers_once_and_prepares_only_one(monkeypatch):
    db=db_session()
    try:
        calls=[]
        def prepare(db, limit, notifier):
            calls.append('prepare')
            if len(calls)==1:return []
            return [{'status':'prepared','has_photo':True,'draft_id':'one'}]
        def discover(db, sources):
            calls.append('discover')
            yield {'feed':'NASA APOD','inserted':1}
        monkeypatch.setattr(web,'prepare_batch',prepare)
        monkeypatch.setattr(research,'discover',discover)
        monkeypatch.setenv('ENABLE_LIVE_PUBLISH','false')
        result=web.generate_test_news(db,None,123)
        assert 'Satu draf dan cover' in result
        assert calls==['prepare','discover','prepare']
    finally:
        db.close()


def test_discovery_reports_empty_feed_and_never_loops(monkeypatch):
    db=db_session()
    try:
        calls=[]
        monkeypatch.setattr(web,'prepare_batch',lambda db,limit,notifier:calls.append('prepare') or [])
        def discover(db,sources):
            calls.append('discover')
            yield {'feed':'NASA APOD','inserted':0}
        monkeypatch.setattr(research,'discover',discover)
        monkeypatch.setenv('ENABLE_LIVE_PUBLISH','false')
        assert 'Belum ada berita baru' in web.generate_test_news(db,None,123)
        assert calls==['prepare','discover']
    finally:
        db.close()


def test_telegram_update_idempotent_after_delivery(monkeypatch):
    db=db_session()
    class Bot:
        def __init__(self):self.messages=[]
        def message(self,chat,text,keyboard=None):self.messages.append(text)
        def answer(self,*args):pass
    try:
        from dataclasses import replace
        bot=Bot()
        monkeypatch.setattr(web,'CONFIG',replace(web.CONFIG,admin_ids=frozenset({42})))
        monkeypatch.setattr(web,'_bot',lambda:bot)
        invocations=[]
        monkeypatch.setattr(web,'generate_test_news',lambda *a:invocations.append('generated') or 'done')
        update={'update_id':12345,'callback_query':{'id':'callback-12345','from':{'id':42},
                 'message':{'chat':{'id':123}},'data':'nav:test_news'}}
        assert web.telegram_webhook(update,db=db)['ok']
        again=web.telegram_webhook(update,db=db)
        assert again['ignored']=='duplicate_telegram_update'
        assert invocations==['generated']
        assert db.get(TelegramUpdateReceipt,'12345') is not None
    finally:
        db.close()
