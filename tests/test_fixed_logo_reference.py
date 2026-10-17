"""Owner reference cover: badge never moves, text adapts below it."""
from PIL import Image, ImageDraw
from utbot.renderer import (
    WIDTH, HEIGHT, SIDE_MARGIN, BOTTOM_MARGIN, BADGE_BOX, HEADLINE_TOP,
    _draw_badge, _headline_layout, _title_draw_y, _font, _ink_height,
    _reference_line_pitch, require_cover_fit, render,
)


def test_logo_coordinates_are_absolute():
    assert BADGE_BOX == (402, 900, 678, 948)
    assert HEADLINE_TOP == 981
    assert HEADLINE_TOP - BADGE_BOX[3] == 33
    assert SIDE_MARGIN == BOTTOM_MARGIN == 56


def test_logo_does_not_move_with_font_size_or_headline_length(tmp_path):
    badge=tmp_path/'badge.png'
    Image.new('RGBA',(276,48),(255,255,255,255)).save(badge)
    for font_size in (48,68,100,132):
        img=Image.new('RGB',(WIDTH,HEIGHT),'black')
        _draw_badge(img,badge)
        assert img.getbbox()==BADGE_BOX
        font=_font(font_size)
        assert _title_draw_y(font,0,_reference_line_pitch(font)) + font.getbbox('HM',anchor='la')[1] == HEADLINE_TOP


def test_adaptive_headlines_keep_fixed_anchor_and_safe_edges():
    draw=ImageDraw.Draw(Image.new('RGB',(WIDTH,HEIGHT)))
    examples=(
        'Fisikawan Temukan Sinyal Aneh Dalam Pencarian Partikel Dark Matter',
        'Satelit NASA Menangkap Hampir Seluruh Indonesia Memerah Pekat Dan Ini Yang Sedang Menyelimuti Langit Kita',
    )
    for title in examples:
        font,lines,pitch=_headline_layout(draw,title)
        assert len(lines)==4
        assert _title_draw_y(font,0,pitch)+font.getbbox('HM',anchor='la')[1]==HEADLINE_TOP
        assert HEADLINE_TOP+3*pitch+_ink_height(font)<=HEIGHT-BOTTOM_MARGIN
        assert len(require_cover_fit(title))==4


def test_render_preserves_reference_logo_and_canvas(tmp_path):
    source=tmp_path/'photo.jpg'
    Image.new('RGB',(1500,1600),'#223344').save(source)
    output=tmp_path/'cover.jpg'
    render(source,'Fisikawan Temukan Sinyal Aneh Dalam Pencarian Partikel Dark Matter',output)
    assert Image.open(output).size==(1080,1350)
