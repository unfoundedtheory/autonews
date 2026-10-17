from types import SimpleNamespace
import pytest
from utbot.accent import manual_green_phrases,cover_accent_phrases,MANUAL_GREEN_MARKER
from utbot.telegram import keyboard


def test_manual_green_selects_exact_existing_headline_words():
    headline='Ilmuwan Menemukan Lubang Hitam di Pusat Galaksi'
    phrases=manual_green_phrases(headline,'Lubang Hitam, Galaksi')
    assert phrases==[MANUAL_GREEN_MARKER,'LUBANG HITAM','GALAKSI']
    assert cover_accent_phrases(headline,phrases)==['LUBANG HITAM','GALAKSI']


def test_manual_green_rejects_nonexistent_or_overlapping_words():
    headline='Ilmuwan Menemukan Lubang Hitam di Pusat Galaksi'
    with pytest.raises(ValueError):
        manual_green_phrases(headline,'Planet Jupiter')
    with pytest.raises(ValueError):
        manual_green_phrases(headline,'Lubang Hitam, Hitam')


def test_pending_preview_offers_green_editor_and_approved_offers_post_now():
    d=SimpleNamespace(id='draft-1',version=3,status='pending_approval',
                      publish_state='unpublished')
    buttons=str(keyboard(d))
    assert 'green:draft-1:3' in buttons
    assert 'postnow:draft-1:3' not in buttons
    d.status='approved'
    buttons=str(keyboard(d))
    assert 'postnow:draft-1:3' in buttons
    assert 'approve:draft-1:3' not in buttons
