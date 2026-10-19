"""Regression test against the exact six owner-provided cover coordinates."""
from pathlib import Path
from PIL import Image, ImageDraw
from utbot.renderer import (
    BADGE_BOX, HEADLINE_TOP, HEADLINE_BOTTOM, TRACKING_EM, LINE_SPACING, WORD_GAP_EM,
    SIDE_MARGIN, BOTTOM_MARGIN, _draw_title_line,
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


def test_badge_is_locked_to_owner_reference_with_uniform_safe_margins():
    assert BADGE_BOX==(402,900,678,948)
    assert HEADLINE_TOP==981
    assert HEADLINE_BOTTOM==1350-56
    assert SIDE_MARGIN==BOTTOM_MARGIN==MARGIN==56
    assert HEADLINE_TOP-BADGE_BOX[3]==33
    assert BADGE_BOX[0]+BADGE_BOX[2]==WIDTH


def test_text_fits_fixed_box_independent_of_line_count():
    draw = ImageDraw.Draw(Image.new('RGB',(1080,1350)))
    counts=[]
    for headline in HEADLINES:
        font, lines, pitch = _headline_layout(draw,headline)
        counts.append(len(lines))
        assert (_title_draw_y(font,0,pitch)+font.getbbox('HM',anchor='la')[1]
                == HEADLINE_TOP)
        assert len(lines) == 4
        assert HEADLINE_TOP+(len(lines)-1)*pitch+_ink_height(font) <= HEADLINE_BOTTOM
        assert all(_line_width(draw,line,font) <= WIDTH-2*MARGIN for line in lines)
    assert counts == [4,4,4,4]
    sizes=[_headline_layout(draw,headline)[0].size for headline in HEADLINES]
    # Font size should not be forced to one value for all different headlines.
    assert len(set(sizes))>=2
    assert min(sizes)>=48


def test_tracking_tightens_characters_but_preserves_real_word_gap():
    font = _font(82)
    draw = ImageDraw.Draw(Image.new('RGB',(1080,1350)))
    assert TRACKING_EM == -0.047
    assert LINE_SPACING == 1.08
    assert _letter_tracking(font) < 0
    assert 0.17 <= WORD_GAP_EM <= 0.24
    assert _word_gap(draw,font) >= 12
    assert _word_gap(draw,font) > -_letter_tracking(font) * 3


def test_badge_stays_fixed_when_headline_font_size_changes():
    from utbot.renderer import _draw_badge
    badges=[]
    for headline in HEADLINES[:3]:
        face,_,pitch=_headline_layout(
            ImageDraw.Draw(Image.new('RGB',(1080,1350))),headline)
        background=Image.new('RGB',(1080,1350),(3,3,3))
        _draw_badge(background)
        badges.append(background.crop((400,900,680,948)))
        assert _title_draw_y(face,0,pitch)+face.getbbox('HM',anchor='la')[1]-948==33
    from PIL import ImageChops
    for badge in badges[1:]:
        assert ImageChops.difference(badge,badges[0]).getbbox() is None


def test_original_photo_top_region_is_not_reinvented(tmp_path):
    # No owner media is required in CI. Test the no-artificial-photo rule
    # using a deterministic synthetic input image.
    photo=tmp_path/'reference.jpg'
    Image.new('RGB',(1080,1350),(60,90,125)).save(photo,quality=100)
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


def test_rendered_ink_stays_inside_equal_side_and_bottom_safe_area():
    """Check actual glyph pixels, not only calculated typeface widths."""
    from PIL import ImageChops
    for headline in HEADLINES + [
        'Gugusan Galaksi Raksasa Ini Membelokkan Cahaya Hingga Menyerupai Rumah Kaca',
        'Kamera Robotik Berhasil Merekam Lingkaran Cahaya Auroral Utuh Dari Luar Angkasa',
    ]:
        canvas=Image.new('RGB',(WIDTH,1350),'#000000')
        draw=ImageDraw.Draw(canvas)
        face,lines,pitch=_headline_layout(draw,headline)
        for i,line in enumerate(lines):
            _draw_title_line(draw,line,_title_draw_y(face,i,pitch),face,set())
        bounds=ImageChops.difference(canvas,Image.new('RGB',canvas.size,'#000000')).getbbox()
        assert bounds is not None and len(lines)==4
        l,t,r,b=bounds
        assert l>=SIDE_MARGIN-4, (headline,'left',l)
        assert WIDTH-r>=SIDE_MARGIN-4,(headline,'right',WIDTH-r)
        assert 1350-b>=BOTTOM_MARGIN,(headline,'bottom',1350-b)
        assert abs(l-(WIDTH-r))<=12,(headline,'optical center',l,WIDTH-r)
        assert t>=HEADLINE_TOP-3,(headline,'top',t)


def test_owner_long_pleiades_hook_reports_undersized_type():
    """Regression from the real cover: legal wrapping is NOT adequate legibility."""
    from utbot.renderer import headline_font_size, MIN_EDITORIAL_FONT_PX
    long_title=('GUGUSAN BINTANG PALING TERKENAL INI TERNYATA MENYIMPAN '
                'SELIMUT DEBU RAKSASA YANG HANYA MUNCUL LEWAT PAJANAN 23 JAM')
    short_title='GUGUSAN BINTANG TERKENAL INI MENYIMPAN SELIMUT DEBU RAKSASA'
    long_px=headline_font_size(long_title)
    short_px=headline_font_size(short_title)
    assert long_px < short_px, (long_px,short_px)
    assert short_px >= MIN_EDITORIAL_FONT_PX, (long_px,short_px)
