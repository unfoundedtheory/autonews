"""Visual identity and public attribution regressions."""
from types import SimpleNamespace
import pytest

from utbot.instagram import photo_credit_line, caption_text
from utbot.renderer import DEFAULT_HEADLINE_FONT, font_readability_status, _font, TRACKING_EM, LINE_SPACING
from utbot.telegram import preview_text

TAGS=['#Astronomi','#NASA','#Sains','#Riset','#UnfoundedTheory']
BODY=(
    'Sesuatu yang aneh terlihat di langit.\n\n'
    'Para astronom memeriksa data penelitian.\n\n'
    'Namun hasilnya masih harus diuji.\n\n'
    'Apa yang akan ditemukan berikutnya?'
)

def draft(*, credit='NASA', photo_url='https://science.nasa.gov/mission', caption=BODY):
    return SimpleNamespace(highlight='Sesuatu yang Aneh Terlihat di Langit',
                           caption=caption,hashtags=TAGS,
                           image_credit=credit,media_page_url=photo_url)

def test_league_spartan_black_is_bundled_and_readable():
    assert DEFAULT_HEADLINE_FONT.is_file(), 'Production must bundle League Spartan TTF'
    font=_font(80)
    assert 'league spartan' in font.getname()[0].casefold()
    assert TRACKING_EM == -0.047 and LINE_SPACING == 1.05
    metrics=font_readability_status()
    assert metrics['readable'] is True
    assert 'league spartan' in metrics['font_family'].casefold()

def test_instagram_caption_has_short_photo_credit_before_last_five_hashtags():
    d=draft()
    assert photo_credit_line(d)=='Photo by : NASA'
    body=caption_text(d)
    assert body.endswith('Photo by : NASA\n\n'+' '.join(TAGS))
    assert body.count('Photo by :')==1
    assert body.count('#')==5

def test_threads_link_resolves_human_confirmed_handle():
    d=draft(credit='@ikhsanaditya_',photo_url='https://www.threads.net/@ikhsanaditya_/post/1234')
    assert photo_credit_line(d)=='Photo by : threads/ikhsanaditya_'
    assert 'Photo by : threads/ikhsanaditya_\n\n#Astronomi' in caption_text(d)

def test_explicit_social_credit_is_preserved_even_without_social_url():
    d=draft(credit='Photo by : threads/ikhsanaditya_')
    assert photo_credit_line(d)=='Photo by : threads/ikhsanaditya_'

def test_credited_creator_does_not_change_to_social_reposter():
    d=draft(credit='Jane Astronomer',photo_url='https://www.threads.net/@repost_account/post/1234')
    assert photo_credit_line(d)=='Photo by : Jane Astronomer'

def test_photo_change_drops_old_embedded_photo_credit():
    d=draft(credit='ESA',caption=BODY+'\n\nPhoto by : Old Photographer')
    body=caption_text(d)
    assert 'Old Photographer' not in body
    assert body.count('Photo by :')==1
    assert body.endswith('Photo by : ESA\n\n'+' '.join(TAGS))

def test_missing_credit_blocks_publishing_but_is_honest_in_telegram_preview():
    d=draft(credit='')
    with pytest.raises(ValueError,match='Kredit foto'):
        caption_text(d)
    preview=preview_text(d,None)
    assert 'Photo by : (kredit foto belum diisi)' in preview
    assert preview.endswith(' '.join(TAGS))

def test_caption_char_limit_includes_credit_and_hashtags():
    d=draft(credit='NASA',caption='a'*2150)
    with pytest.raises(ValueError,match='2.200'):
        caption_text(d)
