"""Regressions for editor-owned literal Telegram hook input."""
from dataclasses import replace
from sqlalchemy.orm import sessionmaker
from utbot.models import Base,make_engine,Story,Draft,TelegramSession,Audit
from utbot.research import fingerprint
from utbot import web
from utbot.telegram import keyboard, advanced_keyboard,preview_text
from utbot.manual_hook import validate_typed_hook,accent_for_hook

ORIGINAL='Fisikawan Temukan Sinyal Aneh Dalam Pencarian Partikel Dark Matter'
CUSTOM='Kalau Kamu Tinggal di Mars Kapan Ulang Tahunmu Tiba Lagi'
CAPTION=('Saat membayangkan kehidupan di Mars, satu tahun terasa berbeda.\n\n'
         'NASA menjelaskan panjang orbit Mars dibanding Bumi.\n\n'
         'Namun jumlah hari tidak sama dengan lamanya satu putaran planet.\n\n'
         'Apa artinya bagi kehidupan seorang manusia di sana?')
TAGS=['#Mars','#NASA','#Astronomi','#Antariksa','#UnfoundedTheory']


class FakeBot:
    def __init__(self):self.messages=[];self.answers=[]
    def message(self,chat,text,reply_markup=None):
        self.messages.append((text,reply_markup))
    def answer(self,*args):self.answers.append(args)


def seed_db():
    engine=make_engine('sqlite://')
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine,expire_on_commit=False)()


def build_story(db):
    url='https://science.nasa.gov/solar-system/planets/mars/'
    st=Story(fingerprint=fingerprint(url),title='Life on Mars and its year',
             source_url=url,source_name='NASA Science',topic='space',
             verification_status='verified',evidence=[
                 {'claim':'Mars year','quote':'The year on Mars is longer than on Earth.'},
                 {'claim':'Mars orbit','quote':'Mars orbits the Sun.'}])
    db.add(st);db.flush()
    d=Draft(story_id=st.id,highlight=ORIGINAL,caption=CAPTION,hashtags=TAGS,
            status='approved',approved_version=1,approved_by='previous_editor',
            image_url='https://example.org/old-approved-cover.jpg',rights_reviewed=True)
    db.add(d);db.commit()
    return st,d


def telegram_callback(d,action):
    return {'callback_query':{'id':'callback-manual','from':{'id':42},
            'message':{'chat':{'id':100}},
            'data':f'{action}:{d.id}:{d.version}'}}


def telegram_text(value):
    return {'message':{'from':{'id':42},'chat':{'id':100},'text':value}}


def configure(monkeypatch):
    bot=FakeBot()
    monkeypatch.setattr(web,'CONFIG',replace(web.CONFIG,admin_ids=frozenset({42}),
                         telegram_token='mock-secret',chat_id='100'))
    monkeypatch.setattr(web,'_bot',lambda:bot)
    return bot


def test_manual_hook_button_and_preview_are_clean():
    db=seed_db()
    try:
        _,d=build_story(db)
        actions=[b['callback_data'] for row in advanced_keyboard(d)['inline_keyboard'] for b in row]
        assert f'manualhook:{d.id}:{d.version}' in actions
        body=preview_text(d,db.get(Story,d.story_id))
        assert body.startswith('HIGHLIGHT\n')
        assert 'CAPTION\n' in body
        assert 'Draf ' not in body
        assert 'Lisensi:' not in body
        assert 'Hak foto:' not in body
    finally:db.close()


def test_manual_hook_sent_as_typed_never_triggers_ai_and_revokes_old_approval(monkeypatch):
    db=seed_db()
    try:
        _,d=build_story(db)
        bot=configure(monkeypatch)
        monkeypatch.setattr(web,'_revision_text',lambda *a,**k: (_ for _ in ()).throw(AssertionError('AI rewrite invoked')))
        assert web.telegram_webhook(telegram_callback(d,'manualhook'),db=db)['ok']
        session=db.get(TelegramSession,'42')
        assert session.mode=='manual_hook' and session.version==1
        assert web.telegram_webhook(telegram_text(CUSTOM),db=db)['ok']
        db.refresh(d)
        assert d.highlight==CUSTOM
        assert d.version==2
        assert d.status=='pending_approval'
        assert d.approved_by is None and d.approved_version is None
        assert d.image_url is None
        assert 'MARS' in d.accent_words
        assert db.get(TelegramSession,'42') is None
        assert db.query(Audit).filter_by(draft_id=d.id,event='manual_hook_submitted').count()==1
        assert any('tanpa perubahan oleh AI' in t for t,_ in bot.messages)
    finally:db.close()


def test_invalid_manual_input_can_be_retried_without_version_bump(monkeypatch):
    db=seed_db()
    try:
        _,d=build_story(db)
        bot=configure(monkeypatch)
        web.telegram_webhook(telegram_callback(d,'manualhook'),db=db)
        web.telegram_webhook(telegram_text('Hook pendek'),db=db)
        db.refresh(d)
        assert d.version==1
        assert db.get(TelegramSession,'42') is not None
        web.telegram_webhook(telegram_text('Jika Kamu Tinggal Di Mars Apakah Sehari Menjadi 48 Jam Selamanya'),db=db)
        db.refresh(d)
        assert d.version==1 and d.highlight==ORIGINAL
        assert any('belum ada dalam bukti sumber' in text for text,_ in bot.messages)
        web.telegram_webhook(telegram_text('/cancel'),db=db)
        assert db.get(TelegramSession,'42') is None
    finally:db.close()


def test_hook_alternative_list_uses_real_line_breaks_and_custom_input_button(monkeypatch):
    db=seed_db()
    try:
        _,d=build_story(db)
        bot=configure(monkeypatch)
        monkeypatch.setattr('utbot.hook_editor.alternatives',lambda *_a:[
            'Fisikawan Mencari Partikel Kosmik Yang Sulit Dilacak di Antartika',
            'Bagaimana Es Antartika Membantu Mengungkap Misteri Kosmik Terbesar'])
        assert web.telegram_webhook(telegram_callback(d,'hookideas'),db=db)['ok']
        msg,kb=next((text,keys) for text,keys in bot.messages if text.startswith('✨ Alternatif'))
        assert '\n\n1. ' in msg and '\n\n2. ' in msg
        assert '\\n' not in msg
        assert any(button['text']=='✍️ Tulis Hook Sendiri'
                   for row in kb['inline_keyboard'] for button in row)
        assert db.get(TelegramSession,'42').mode=='manual_hook'
        # Typing immediately after seeing AI options is treated literally.
        monkeypatch.setattr(web,'_revision_text',lambda *a,**k: (_ for _ in ()).throw(AssertionError('AI rewrite invoked')))
        web.telegram_webhook(telegram_text(CUSTOM),db=db)
        db.refresh(d)
        assert d.highlight==CUSTOM
        assert d.version==2
    finally:db.close()


def test_manual_validator_preserves_punctuation_and_checks_unverified_numbers():
    db=seed_db()
    try:
        st,_=build_story(db)
        assert validate_typed_hook(CUSTOM,st)==CUSTOM
        assert accent_for_hook(CUSTOM)==['MARS']
        import pytest
        with pytest.raises(ValueError,match='Angka 48'):
            validate_typed_hook('Jika Kamu Tinggal Di Mars Apakah Sehari Menjadi 48 Jam Selamanya',st)
    finally:db.close()


def test_manual_hook_owner_approval_does_not_require_fresh_style_qc(monkeypatch):
    import pytest
    from utbot.editorial import approve
    db=seed_db()
    try:
        st,d=build_story(db)
        configure(monkeypatch)
        web.telegram_webhook(telegram_callback(d,'manualhook'),db=db)
        web.telegram_webhook(telegram_text(CUSTOM),db=db)
        db.refresh(d)
        # Final owner approval skips stylistic QC but retains evidence/cover gates.
        d.rights_reviewed=True
        d.image_url='https://example.org/final-v2.jpg'
        d.photo_license='CC BY 4.0'
        d.image_credit='NASA'
        st.evidence=[
            {'claim':'Mars year','quote':'The year on Mars is longer than on Earth.',
             'url':st.source_url,'evidence_checked':True},
            {'claim':'Mars orbit','quote':'Mars orbits the Sun.',
             'url':st.source_url,'evidence_checked':True}]
        approve(db,d,'42')
        assert d.status=='approved' and d.approved_version==d.version
    finally:db.close()


def test_editor_photo_url_never_autofills_fake_license_or_credit(monkeypatch, tmp_path):
    db=seed_db()
    try:
        _,d=build_story(db)
        configure(monkeypatch)
        monkeypatch.setattr('utbot.renderer.require_cover_fit',lambda *args:())
        monkeypatch.setattr(web,'intake_image',
                            lambda url,path: str(tmp_path/'source.jpg'))
        monkeypatch.setattr('utbot.media.render_draft',
                            lambda draft:setattr(draft,'image_url',
                                                 'https://example.org/final.jpg'))
        web._replace_photo(db,d,'https://example.org/user-photo.jpg','42')
        assert d.image_credit is None and d.photo_license is None
        assert not d.rights_reviewed
        assert d.status=='pending_approval'
    finally:
        db.close()


def test_approved_unpublished_draft_can_redraw_with_new_font(monkeypatch):
    db=seed_db()
    try:
        _,d=build_story(db)
        bot=configure(monkeypatch)
        d.source_image_url='https://example.org/science-photo.jpg'
        d.scheduled_at=None
        buttons=[b['callback_data'] for row in advanced_keyboard(d)['inline_keyboard'] for b in row]
        assert f'redesign:{d.id}:{d.version}' in buttons
        monkeypatch.setattr(web,'render_draft',
                            lambda draft:setattr(draft,'image_url',
                                                 'https://example.org/cover-new-font.jpg'))
        monkeypatch.setattr(web,'send_preview',lambda *args:None)
        assert web.telegram_webhook(telegram_callback(d,'redesign'),db=db)['ok']
        db.refresh(d)
        assert d.version==2
        assert d.status=='pending_approval'
        assert d.approved_version is None
        assert d.approved_by is None
        assert d.image_url=='https://example.org/cover-new-font.jpg'
        assert any('Approval dan jadwal sebelumnya dibatalkan' in text
                   for text,_ in bot.messages)
    finally:
        db.close()
