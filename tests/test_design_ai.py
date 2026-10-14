import json
from pathlib import Path
from PIL import Image, ImageDraw
import pytest
import httpx
from utbot.renderer import render, _balanced_wrap, _font
from utbot.ai_provider import generate_json


def test_renderer_keeps_4_5_and_rejects_small_images(tmp_path):
    image = tmp_path / 'photo.jpg'
    Image.new('RGB', (1500, 2000), '#0d1934').save(image)
    out = tmp_path / 'result.jpg'
    assert render(image, 'Inilah Tangan Tuhan Struktur Sinar-X Raksasa Yang Masih Membingungkan NASA',out,
                  accent_words=['TANGAN TUHAN','SINAR-X','RAKSASA']) == str(out)
    assert Image.open(out).size == (1080,1350)
    small = tmp_path / 'small.jpg'
    Image.new('RGB', (500, 1000)).save(small)
    with pytest.raises(ValueError, match='terlalu kecil'):
        render(small, 'Headline', tmp_path / 'small-output.jpg')


def test_renderer_validates_crop_and_labels_illustration(tmp_path):
    image = tmp_path / 'photo.jpg'
    Image.new('RGB', (1080, 1350), '#222233').save(image)
    with pytest.raises(ValueError, match='photo_focus'):
        render(image, 'Pemandangan Langit Ini Memperlihatkan Fenomena Misterius Yang Masih Diteliti Para Ilmuwan', tmp_path/'o.jpg', photo_focus=(1.5,0))
    assert Path(render(image, 'Pemandangan Langit Ini Memperlihatkan Fenomena Misterius Yang Masih Diteliti Para Ilmuwan', tmp_path/'art.jpg',
                       source_type='illustration')).exists()


def test_balanced_wrap_can_fit_long_headline_without_single_last_word():
    words = 'INILAH TANGAN TUHAN STRUKTUR SINAR-X RAKSASA YANG MASIH MEMBINGUNGKAN NASA'.split()
    lines = _balanced_wrap(ImageDraw.Draw(Image.new('RGB',(1080,1350))),words,_font(76),968)
    assert 3 <= len(lines) <= 6
    assert len(lines[-1].split()) > 1


def test_gemini_gateway_mock(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY','test-placeholder')
    monkeypatch.setenv('AI_PROVIDER','gemini')
    def handler(request):
        assert 'generativelanguage.googleapis.com' == request.url.host
        assert request.headers['x-goog-api-key'] == 'test-placeholder'
        body=json.loads(request.content)
        assert body['generationConfig']['responseMimeType']=='application/json'
        return httpx.Response(200,json={'candidates':[{'content':{'parts':[{'text':'{"text":"Valid."}'}]}}]})
    assert generate_json('Editor factual',{'title':'test'}, transport=httpx.MockTransport(handler))['text']=='Valid.'


def test_gemini_quota_failure_never_implicitly_bills_deepseek(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY','test-placeholder')
    monkeypatch.setenv('DEEPSEEK_API_KEY','another-test-placeholder')
    monkeypatch.setenv('AI_PROVIDER','gemini')
    transport = httpx.MockTransport(lambda req:httpx.Response(429,json={'error':'quota'}))
    with pytest.raises(httpx.HTTPStatusError):
        generate_json('system',{'news':'test'},transport=transport)


def test_serverless_font_fallback_is_truly_scalable(monkeypatch,tmp_path):
    from utbot import renderer
    from PIL import ImageFont
    original=renderer.ImageFont.truetype
    # Simulate Vercel: no system fonts are available.
    monkeypatch.setattr(renderer.Path,'is_file',lambda _path:False)
    renderer._font.cache_clear()
    try:
        fallback=renderer._font(78)
        assert fallback.size>=70
        assert renderer._ink_height(fallback)>=45
        heading='Kalau Kamu Tinggal di Mars Kapan Ulang Tahunmu Tiba Lagi'
        assert renderer.cover_fits(heading)
        bg=tmp_path/'hero.jpg'; out=tmp_path/'ready.jpg'
        Image.new('RGB',(1080,1350),'#181818').save(bg)
        renderer.render(bg,heading,out,accent_words=['MARS'])
        crop=Image.open(out).crop((100,980,980,1308))
        bright=sum(1 for p in crop.getdata() if min(p)>185)
        assert bright>3500, 'Headline still rendered as tiny text'
    finally:
        renderer._font.cache_clear()


def test_words_have_physical_gap_not_just_unicode_spaces():
    from utbot.renderer import _word_gap, _word_width, _line_width, _draw_title_line, WIDTH, MARGIN
    canvas = Image.new('RGB',(1080,1350),'#000000')
    draw = ImageDraw.Draw(canvas)
    font = _font(74)
    assert round(font.size*.18) <= _word_gap(draw,font) <= round(font.size*.25)
    line = 'MEMBINGUNGKAN NASA'
    x0,x1 = _draw_title_line(draw,line,1100,font,set())
    assert x0 >= MARGIN
    assert x1 <= WIDTH - MARGIN
    expected_gap = _line_width(draw,line,font) - _word_width(draw,'MEMBINGUNGKAN',font) - _word_width(draw,'NASA',font)
    assert 12 <= expected_gap < 24


def test_quoted_hook_does_not_break_across_lines():
    from utbot.renderer import _headline_tokens, _headline_layout
    highlight="NASA Memotret 'Tangan Tuhan' di Angkasa, Tapi Apa Sebenarnya Struktur Ini?"
    tokens=_headline_tokens(highlight)
    assert "'TANGAN TUHAN'" in tokens
    _,lines,_ = _headline_layout(ImageDraw.Draw(Image.new('RGB',(1080,1350))),highlight)
    assert any("'TANGAN TUHAN'" in line for line in lines)
    assert not any(line.endswith("'TANGAN") or line.startswith("TUHAN'") for line in lines)


def test_headline_never_uses_an_orphan_final_word():
    from utbot.renderer import _headline_layout
    draw=ImageDraw.Draw(Image.new('RGB',(1080,1350)))
    _,lines,_=_headline_layout(draw,'Inilah Tangan Tuhan, Struktur Sinar-X Raksasa Yang Masih Membingungkan NASA')
    assert len(lines[-1].split()) > 1
    assert lines[-1] == 'MEMBINGUNGKAN NASA'
