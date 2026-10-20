"""Production Telegram home-menu regression tests, with no real Telegram or AI traffic."""
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy.orm import sessionmaker

from utbot.models import Base, Draft, Story, make_engine
from utbot.research import fingerprint
from utbot.telegram import main_menu
from utbot.telegram_ui import approved_page, stories_page
from utbot import web


def session():
    engine = make_engine('sqlite://')
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


class FakeTelegram:
    def __init__(self):
        self.messages = []
        self.answers = []
        self.edits = []

    def message(self, chat_id, text, reply_markup=None):
        self.messages.append((text, reply_markup))

    def answer(self, *args):
        self.answers.append(args)

    def call(self, action, data):
        self.edits.append((action, data))


def update(action, message_id=91):
    return {'callback_query': {
        'id': 'callback42', 'from': {'id': 42},
        'message': {'chat': {'id': 123}, 'message_id': message_id},
        'data': 'nav:' + action}}


def test_home_has_only_real_production_actions():
    actions = [item['callback_data']
               for row in main_menu()['inline_keyboard'] for item in row]
    assert len(actions) == len(set(actions)) == 7
    assert set(actions) == {
        'nav:pending', 'nav:approved', 'nav:queue',
        'nav:stories', 'nav:status', 'nav:home', 'nav:generate_now'}
    assert all('test' not in item for item in actions)


def test_approved_pagination_and_posting_state():
    rows = [SimpleNamespace(id=str(uuid4()), version=3,
                highlight='Penjelasan Ilmiah yang Kini Menjadi Sorotan',
                publish_state='manual_music_pending' if i == 0 else 'unpublished',
                scheduled_at=None) for i in range(7)]
    text, menu = approved_page(rows[:5], 7, 0)
    assert 'Halaman 1/2' in text
    assert 'Menunggu konfirmasi posting Instagram' in text
    assert 'nav:approved:1' in str(menu)
    assert len([x for row in menu['inline_keyboard'] for x in row
                if x.get('callback_data','').startswith('open:')]) == 5
    text, menu = approved_page(rows[5:], 7, 1)
    assert 'Halaman 2/2' in text
    assert 'nav:approved:0' in str(menu)


def test_stories_list_only_links_to_trusted_primary():
    rows = [
        SimpleNamespace(title='Riset NASA',
            source_name='NASA', verification_status='needs_fact_check',
            source_url='https://science.nasa.gov/science/'),
        SimpleNamespace(title='Tidak Tepercaya',
            source_name='unknown', verification_status='needs_fact_check',
            source_url='https://untrusted.example/'),
    ]
    text, menu = stories_page(rows, 2)
    assert '2 artikel tercatat' in text
    assert 'Riset NASA' in text
    buttons = [button for row in menu['inline_keyboard'] for button in row]
    assert len([x for x in buttons if 'url' in x]) == 1
    assert buttons[0]['url'] == rows[0].source_url


def test_webhook_approved_and_story_navigation(monkeypatch):
    db = session()
    bot = FakeTelegram()
    monkeypatch.setattr(web, '_bot', lambda: bot)
    monkeypatch.setattr(web, 'CONFIG', replace(web.CONFIG, admin_ids=frozenset({42})))
    try:
        url = 'https://science.nasa.gov/observations/2026/'
        story = Story(fingerprint=fingerprint(url), title='NASA Observatory Science',
                      source_url=url, source_name='NASA', topic='astronomy')
        db.add(story)
        db.flush()
        draft = Draft(story_id=story.id, highlight='A Scientific Discovery Explained',
                      caption='News for testing', hashtags=[], status='approved',
                      approved_version=1, publish_state='manual_music_pending',
                      approved_at=datetime.now(timezone.utc))
        db.add(draft)
        db.commit()

        assert web.telegram_webhook(update('approved'), db=db)['menu'] == 'approved'
        assert 'Draft Disetujui' in bot.messages[-1][0]
        assert f'open:{draft.id}:{draft.version}' in str(bot.messages[-1][1])

        assert web.telegram_webhook(update('stories'), db=db)['menu'] == 'stories'
        assert 'Kandidat Berita' in bot.messages[-1][0]
        assert url in str(bot.messages[-1][1])
    finally:
        db.close()


def test_old_buttons_and_slash_commands_cannot_run_demo(monkeypatch):
    db = session()
    bot = FakeTelegram()
    monkeypatch.setattr(web, '_bot', lambda: bot)
    monkeypatch.setattr(web, 'CONFIG', replace(web.CONFIG, admin_ids=frozenset({42})))

    def prohibited(*args, **kwargs):
        raise AssertionError('Legacy button triggered an AI/demo routine!')

    monkeypatch.setattr(web, 'generate_test_news', prohibited)
    monkeypatch.setattr(web, 'generate_test_cover', prohibited)
    monkeypatch.setattr(web, 'gemini_test_message', prohibited)
    try:
        for old in ('test_gemini', 'test_news', 'test_cover'):
            result = web.telegram_webhook(update(old, message_id=92), db=db)
            assert result['deprecated_menu'] == old
            assert bot.edits[-1][0] == 'editMessageReplyMarkup'
            assert bot.edits[-1][1]['reply_markup'] == main_menu()
            assert 'menu operasional' in bot.messages[-1][0].lower()
        for old in ('/testnews', '/testgemini', '/testcover'):
            message = {'message': {
                'from': {'id': 42}, 'chat': {'id': 123}, 'text': old}}
            assert web.telegram_webhook(message, db=db)['deprecated_command'] == old[1:]
            assert 'dinonaktifkan' in bot.messages[-1][0]
    finally:
        db.close()


def test_generate_now_uses_real_pipeline_and_keeps_approval_required(monkeypatch):
    db = session()
    bot = FakeTelegram()
    monkeypatch.setattr(web, '_bot', lambda: bot)
    monkeypatch.setattr(web, 'CONFIG', replace(web.CONFIG, admin_ids=frozenset({42})))
    calls=[]
    def generate(db, b, chat_id):
        calls.append((b, chat_id))
        return '✅ Draft dibuat. Menunggu approval.'
    monkeypatch.setattr(web, 'generate_news_now', generate)
    try:
        response=web.telegram_webhook(update('generate_now'), db=db)
        assert response['menu']=='generate_now'
        assert calls == [(bot, 123)]
        assert 'Menunggu approval' in bot.messages[-1][0]
    finally:
        db.close()


def test_queue_includes_overdue_and_future_unpublished_approved_posts(monkeypatch):
    from datetime import timedelta
    db=session()
    bot=FakeTelegram()
    monkeypatch.setattr(web,'_bot',lambda:bot)
    monkeypatch.setattr(web,'CONFIG',replace(web.CONFIG,admin_ids=frozenset({42})))
    now=datetime.now(timezone.utc)
    try:
        for i,(offset,status,publish_state) in enumerate([
            (-60,'approved','unpublished'),
            (60,'approved','unpublished'),
            (90,'published','published'),
            (120,'pending_approval','unpublished'),
        ]):
            url=f'https://science.nasa.gov/test-queue-{i}'
            story=Story(fingerprint=fingerprint(url),title='Queue fixture',
                        source_url=url,source_name='NASA',topic='astronomy')
            db.add(story);db.flush()
            db.add(Draft(story_id=story.id,highlight=f'Queue test {i}',
                         caption='Fixture',hashtags=[],status=status,
                         approved_version=1 if status!='pending_approval' else None,
                         publish_state=publish_state,
                         scheduled_at=now+timedelta(minutes=offset)))
        db.commit()
        result=web.telegram_webhook(update('queue'),db=db)
        assert result['menu']=='queue'
        text=bot.messages[-1][0]
        assert 'Queue test 1' in text
        assert 'Queue test 0' in text
        assert 'TERLAMBAT / BELUM TERBIT' in text
        assert 'Queue test 2' not in text
        assert 'Queue test 3' not in text
        assert bot.messages[-1][1]['inline_keyboard'][-1][0]['callback_data']=='nav:home'
    finally:
        db.close()


def test_queue_post_now_overrides_future_slot_and_targets_single_draft(monkeypatch):
    from datetime import timedelta
    from utbot.models import Audit
    db=session()
    bot=FakeTelegram()
    monkeypatch.setattr(web,'_bot',lambda:bot)
    monkeypatch.setattr(web,'CONFIG',replace(web.CONFIG,admin_ids=frozenset({42}),
                        photo_music_mode='off',live_publish=True))
    now=datetime.now(timezone.utc)
    try:
        url='https://science.nasa.gov/test-post-now/'
        story=Story(fingerprint=fingerprint(url),title='New science',
                    source_url=url,source_name='NASA',topic='astronomy')
        db.add(story);db.flush()
        draft=Draft(story_id=story.id,highlight='Scheduled astronomy news',
                    caption='Caption',hashtags=[],status='approved',approved_version=1,
                    publish_state='unpublished',scheduled_at=now+timedelta(days=1))
        db.add(draft);db.flush()
        db.add(Audit(draft_id=draft.id,event='photo_only_approved',actor='42',
                     detail={'version':1}))
        db.commit()
        web.telegram_webhook(update('queue'),db=db)
        assert f'postnow:{draft.id}:1' in str(bot.messages[-1][1])
        calls=[]
        monkeypatch.setattr(web,'publish_job',lambda *,db,target_draft_id:
                            (calls.append(target_draft_id) or {'waiting':target_draft_id}))
        payload={'callback_query':{'id':'cb','from':{'id':42},
                 'message':{'chat':{'id':123}},'data':f'postnow:{draft.id}:1'}}
        assert web.telegram_webhook(payload,db=db)['instagram_retry']
        assert calls==[draft.id]
        assert draft.scheduled_at<=datetime.now(timezone.utc)
        draft.publish_state='published';draft.status='published';db.commit()
        web.telegram_webhook(update('queue'),db=db)
        assert 'postnow:' not in str(bot.messages[-1][1])
    finally:
        db.close()


def test_submenus_have_single_home_button_that_opens_start_menu(monkeypatch):
    db=session()
    bot=FakeTelegram()
    monkeypatch.setattr(web,'_bot',lambda:bot)
    monkeypatch.setattr(web,'CONFIG',replace(web.CONFIG,admin_ids=frozenset({42})))
    try:
        for action in ('pending','approved','stories','queue','status'):
            assert web.telegram_webhook(update(action),db=db)['menu']==action
            buttons=[button for row in bot.messages[-1][1]['inline_keyboard']
                     for button in row]
            assert [b['callback_data'] for b in buttons].count('nav:home')==1
            assert buttons[-1]['text']=='🏠 Menu Utama'
            assert not any(b['callback_data']=='nav:generate_now' for b in buttons)
        assert web.telegram_webhook(update('home'),db=db)['menu']=='home'
        assert bot.messages[-1][1]==main_menu()
    finally:
        db.close()


def test_home_button_does_not_duplicate_existing_navigation():
    from utbot.telegram import with_home_button
    menu={'inline_keyboard':[[{'text':'🏠 Menu Utama','callback_data':'nav:home'}]]}
    assert with_home_button(menu)==menu
