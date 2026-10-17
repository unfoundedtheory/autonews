"""Owner-supplied cover reference: logo stays at x402..678, y900..948."""
from PIL import Image, ImageDraw
from utbot import renderer


def test_logo_and_text_reference_grid_are_fixed():
    assert (renderer.WIDTH, renderer.HEIGHT)==(1080,1350)
    assert renderer.BADGE_BOX==(402,900,678,948)
    assert renderer.HEADLINE_TOP==981
    assert renderer.HEADLINE_BOTTOM==1294
    assert renderer.MARGIN==renderer.SIDE_MARGIN==renderer.BOTTOM_MARGIN==56


def test_logo_pixels_never_shift_with_headline_size():
    short='NASA Menemukan Fenomena Aneh di Langit Indonesia'
    long=('Satelit NASA Menangkap Hampir Seluruh Indonesia '
          'Memerah Pekat dan Ini Yang Sedang Menyelimuti Langit Kita')
    draw=ImageDraw.Draw(Image.new('RGB',(1080,1350)))
    for headline in (short,long):
        font,lines,pitch=renderer._headline_layout(draw,headline)
        assert len(lines)==4
        assert renderer._headline_vertical_shift(font,pitch)==0
        assert renderer._title_draw_y(font,0,pitch)+font.getbbox('HM',anchor='la')[1]==981
        assert 981+3*pitch+renderer._ink_height(font)<=1294
        assert all(renderer._line_width(draw,line,font)<=968 for line in lines)
        canvas=Image.new('RGB',(1080,1350),'#000000')
        renderer._draw_badge(canvas,vertical_shift=250)
        # Even callers passing the obsolete shift cannot move the badge.
        assert canvas.crop((402,900,678,948)).getbbox() is not None
        assert canvas.crop((0,0,1080,900)).getbbox() is None
        assert canvas.crop((0,948,1080,1350)).getbbox() is None
