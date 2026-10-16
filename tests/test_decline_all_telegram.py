"""Bulk rejection requires a separate Yes confirmation and never alters approved drafts."""
from dataclasses import replace
from utbot.models import Base, make_engine, Story, Draft
from utbot.research import fingerprint
from utbot import web
from sqlalchemy.orm import sessionmaker


def make_db():
    engine = make_engine('sqlite://')
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


class FakeBot:
    def __init__(self):
        self.messages, self.answers = [], []
    def message(self, chat_id, text, reply_markup=None):
        self.messages.append((text, reply_markup))
    def answer(self, *args):
        self.answers.append(args)


def callback(action):
    return {'callback_query': {'id': 'cb', 'from': {'id': 42},
        'message': {'chat': {'id': 123}}, 'data':'nav:'+action}}


def setup(monkeypatch):
    bot = FakeBot()
    monkeypatch.setattr(web, '_bot', lambda:bot)
    monkeypatch.setattr(web, 'CONFIG', replace(web.CONFIG, admin_ids=frozenset({42})))
    db = make_db()
    for i, status in enumerate(['pending_approval','pending_approval','approved','published']):
        url = f'https://science.nasa.gov/item-{i}/'
        story = Story(fingerprint=fingerprint(url), title=f'News {i}',
                      source_url=url, source_name='NASA', topic='astronomy')
        db.add(story)
        db.flush()
        db.add(Draft(story_id=story.id, highlight=f'Headline {i}',
                     caption='Caption', hashtags=[], status=status))
    db.commit()
    return db, bot


def test_decline_all_cancel_keeps_all_drafts(monkeypatch):
    db,bot=setup(monkeypatch)
    try:
        text, menu = web.pending_page([], 2)
        assert 'nav:decline_all' in str(menu)
        assert web.telegram_webhook(callback('decline_all'), db=db)['confirm_decline_all']==2
        assert 'nav:decline_confirm:2' in str(bot.messages[-1][1])
        assert 'nav:decline_cancel' in str(bot.messages[-1][1])
        assert web.telegram_webhook(callback('decline_cancel'), db=db)['decline_cancelled']
        assert [d.status for d in db.query(Draft).order_by(Draft.highlight)] == [
            'pending_approval','pending_approval','approved','published']
    finally:
        db.close()


def test_decline_all_yes_only_rejects_pending(monkeypatch):
    db,bot=setup(monkeypatch)
    try:
        assert web.telegram_webhook(callback('decline_all'),db=db)['confirm_decline_all']==2
        assert all(d.status!='rejected' for d in db.query(Draft))
        assert web.telegram_webhook(callback('decline_confirm:2'),db=db)['declined']==2
        statuses=[d.status for d in db.query(Draft).order_by(Draft.highlight)]
        assert statuses==['rejected','rejected','approved','published']
        assert web.telegram_webhook(callback('decline_confirm:2'),db=db)['confirmation_expired']
    finally:
        db.close()


def test_decline_all_confirmation_expires_when_count_changes(monkeypatch):
    db,_=setup(monkeypatch)
    try:
        assert web.telegram_webhook(callback('decline_all'),db=db)['confirm_decline_all']==2
        draft=db.query(Draft).filter(Draft.status=='pending_approval').first()
        draft.status='rejected'
        db.commit()
        assert web.telegram_webhook(callback('decline_confirm:2'),db=db)['confirmation_expired']
        assert db.query(Draft).filter(Draft.status=='pending_approval').count()==1
    finally:
        db.close()
