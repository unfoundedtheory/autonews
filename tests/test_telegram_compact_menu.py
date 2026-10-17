"""Compact Telegram editor keyboard with advanced actions on demand."""
from types import SimpleNamespace
from utbot.telegram import keyboard, advanced_keyboard


def fake_draft(**changes):
    values=dict(id='123',version=1,status='pending_approval',
        publish_state='unpublished',approved_by=None,
        image_url='https://example.com/photo.jpg',image_local_path=None,
        source_image_url='https://example.com/source.jpg',
        photo_license=None,image_credit=None,last_error=None)
    values.update(changes)
    return SimpleNamespace(**values)


def actions(buttons):
    return [b['callback_data'].split(':')[0]
            for line in buttons['inline_keyboard'] for b in line
            if 'callback_data' in b]


def test_preview_is_six_buttons_only():
    draft=fake_draft()
    visible=actions(keyboard(draft))
    assert visible==['approve','reject','highlight','caption','photo','more']
    assert not {'hookideas','manualhook','credit','redesign','qc'}.intersection(visible)


def test_lainnya_contains_optional_actions_and_back():
    draft=fake_draft()
    options=actions(advanced_keyboard(draft))
    assert {'hookideas','manualhook','credit','redesign','sources','qc','actions'}<=set(options)
    assert len(options)==len(set(options))


def test_approved_draft_does_not_show_old_approve_button():
    draft=fake_draft(status='approved',publish_state='published')
    assert actions(keyboard(draft))==['more']


def test_approved_unpublished_has_photo_recovery_not_music_actions(monkeypatch):
    from utbot import config
    from dataclasses import replace
    monkeypatch.setattr(config,'CONFIG',replace(config.CONFIG,photo_music_mode='off'))
    draft=fake_draft(status='approved',publish_state='unpublished')
    options=actions(advanced_keyboard(draft))
    assert 'retryig' in options
    assert 'musicdone' not in options
    assert 'musickit' not in options
