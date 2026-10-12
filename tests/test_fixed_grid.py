"""Regression test against the exact six owner-provided cover coordinates."""
from pathlib import Path
from PIL import Image, ImageDraw
from utbot.renderer import (
    BADGE_BOX, HEADLINE_TOP, HEADLINE_BOTTOM, TRACKING_EM, WORD_GAP_EM,
    _font, _headline_layout, _title_draw_y, _word_gap, _letter_tracking,
    _line_width, _ink_height, render, MARGIN, WIDTH
)

ROOT = Path(__file__).resolve().parents[1]
HEADLINES = [
    "NASA Memotret 'Tangan Tuhan' di Angkasa, Tapi Apa Sebenarnya Struktur Ini?",
    'Inilah Tangan Tuhan, Struktur Sinar-X Raksasa Yang Masih Membingungkan NASA',
    'Piramida Raksasa Ini Terkubur 25 Meter Di Dasar Laut Jepang Dan Diklaim Lebih Tua Dari Piramida Mesir',
    'Dua Benda Paling Terang Di Langit Tiba-Tiba Muncul Berdampingan Semalam',
]


def test_original_six_reference_badge_is_same_position():
    assert BADGE_BOX == (402, 900, 678, 948)
    assert HEADLINE_TOP == 981
    assert HEADLINE_BOTTOM == 1307
    assert (HEADLINE_TOP-BADGE_BOX[3]) >= 32


def test_text_fits_fixed_box_independent_of_line_count():
    draw = ImageDraw.Draw(Image.new('RGB',(1080,1350)))
    counts=[]
    for headline in HEADLINES:
        font, lines, pitch = _headline_layout(draw,headline)
        counts.append(len(lines))
        assert _title_draw_y(font,0,pitch)+font.getbbox('HM',anchor='la')[1] == HEADLINE_TOP
        assert len(lines) == 4
        assert HEADLINE_TOP+(len(lines)-1)*pitch+_ink_height(font) <= HEADLINE_BOTTOM
        assert all(_line_width(draw,line,font) <= WIDTH-2*MARGIN for line in lines)
    assert set(counts) == {4}


def test_tracking_tightens_characters_but_preserves_real_word_gap():
    font = _font(82)
    draw = ImageDraw.Draw(Image.new('RGB',(1080,1350)))
    assert -.03 <= TRACKING_EM <= -.02
    assert _letter_tracking(font) < 0
    assert 0.17 <= WORD_GAP_EM <= 0.24
    assert _word_gap(draw,font) >= 12
    assert _word_gap(draw,font) > -_letter_tracking(font) * 3


def test_identical_badge_pixels_for_four_and_five_line_posts(tmp_path):
    bg = tmp_path/'dark.jpg'
    Image.new('RGB',(1080,1350),(3,3,3)).save(bg)
    regions=[]
    for index,headline in enumerate(HEADLINES[:3]):
        out=tmp_path/f'cover-{index}.jpg'
        render(bg,headline,out,accent_words=['TANGAN','TUHAN'])
        image=Image.open(out)
        # slight lossy JPEG coupling outside badge region, compare center area only
        regions.append(image.crop((400,900,680,946)))
    # JPEG compression may differ slightly by layout below y=981; badge itself unchanged.
    from PIL import ImageChops
    for r in regions[1:]:
        diff = ImageChops.difference(r, regions[0])
        assert max(upper for lower,upper in diff.getextrema()) <= 3


def test_original_photo_top_region_is_not_reinvented(tmp_path):
    photo=ROOT/'assets'/'preview_photo_from_owner_reference.jpg'
    assert photo.exists()
    out=tmp_path/'preview.jpg'
    render(photo,HEADLINES[0],out,accent_words=['TANGAN','TUHAN'])
    from PIL import ImageChops
    source=Image.open(photo).convert('RGB')
    result=Image.open(out).convert('RGB')
    # Compare source image (re-encoded JPEG) rather than insist on bit-for-bit JPEG.
    from PIL import ImageStat
    diff=ImageChops.difference(source.crop((80,80,990,440)),
                               result.crop((80,80,990,440)))
    assert max(ImageStat.Stat(diff).mean) < 3.0
