"""Owner design contract: League Spartan Bold 700 and semantic spaced accents."""
from PIL import Image
from utbot import renderer
from utbot.accent import accent_for_hook

HEADLINE='Kamera Robotik Berhasil Merekam Lingkaran Cahaya Auroral Utuh Dari Luar Angkasa'


def test_screenshot_headline_highlights_subject_action_phenomenon():
    # A legacy 1-word "LINGKARAN" selection should be corrected automatically.
    assert accent_for_hook(HEADLINE,['LINGKARAN']) == [
        'KAMERA ROBOTIK','MEREKAM','AURORAL']
    assert accent_for_hook(HEADLINE,[]) == [
        'KAMERA ROBOTIK','MEREKAM','AURORAL']


def test_scientific_phenomenon_can_be_a_short_word_or_phrase():
    assert 'MARS' in accent_for_hook(
        'Kalau Kamu Tinggal Di Mars Kapan Ulang Tahunmu Akan Datang Lagi')
    phrase=accent_for_hook(
        'Fisikawan Temukan Sinyal Aneh Dalam Pencarian Partikel Dark Matter',
        ['SINYAL'])
    assert 'DARK MATTER' in phrase
    assert all(len(x.split())<=2 for x in phrase)


def test_true_league_spartan_bold_seven_hundred():
    font=renderer._font(80)
    family,style=font.getname()
    assert 'league spartan' in family.casefold()
    # Variation face must not be stuck on Black 900 or unbold Regular.
    assert 'bold' in style.casefold()
    assert 'black' not in style.casefold()
    assert renderer.TRACKING_EM == -0.047
    assert renderer.LINE_SPACING == 1.05


def test_renderer_uses_all_three_accents_in_real_cover(tmp_path,monkeypatch):
    src=tmp_path/'science.jpg'
    Image.new('RGB',(1080,1350),'#263240').save(src)
    out=tmp_path/'cover.jpg'
    recorded=[]
    original=renderer._draw_word_tracked

    def track(draw,word,x,y,font,color):
        recorded.append((word,color))
        return original(draw,word,x,y,font,color)
    monkeypatch.setattr(renderer,'_draw_word_tracked',track)
    renderer.render(src,HEADLINE,out,accent_words=['LINGKARAN'])
    assert Image.open(out).size == (1080,1350)
    green={word for word,color in recorded if color==renderer.GREEN}
    assert green=={'KAMERA','ROBOTIK','MEREKAM','AURORAL'}
    assert ('LINGKARAN',renderer.WHITE) in recorded
