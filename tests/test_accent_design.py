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
    from PIL import ImageFont
    font=renderer._font(96)
    assert 'league spartan' in font.getname()[0].casefold()
    assert font.get_variation_axes()[0]['minimum']<=700<=font.get_variation_axes()[0]['maximum']

    # Some FreeType/Pillow releases keep returning the VARIABLE FONT's
    # base style name ('Thin') even after selecting its 700 weight. Compare
    # actual rasterized glyph weight, not a stale metadata label.
    def ink_at(weight):
        f=ImageFont.truetype(renderer.DEFAULT_HEADLINE_FONT,96)
        f.set_variation_by_axes([weight])
        return sum(bytes(f.getmask('MMMM')))

    active=sum(bytes(font.getmask('MMMM')))
    regular=ink_at(400)
    black=ink_at(900)
    assert regular<active<black, (regular,active,black)
    assert active==ink_at(700)
    assert renderer.TRACKING_EM == -0.047
    assert renderer.LINE_SPACING == 1.08


def test_long_reference_maximizes_font_and_preserves_semantic_accents(tmp_path,monkeypatch):
    from PIL import ImageDraw
    headline=('Piramida Raksasa Ini Terkubur 25 Meter Di Dasar '
              'Laut Jepang Dan Diklaim Lebih Tua Dari Piramida Mesir')
    font,lines,pitch=renderer._headline_layout(
        ImageDraw.Draw(Image.new('RGB',(1080,1350))),headline)
    assert 2<=len(lines)<=5
    assert 48<=font.size<=144
    assert pitch==renderer._reference_line_pitch(font)
    # The actual line height scales with the dynamically selected font size.
    assert 30<=renderer._ink_height(font)<=85
    assert renderer.HEADLINE_TOP+(len(lines)-1)*pitch+renderer._ink_height(font)<=renderer.HEADLINE_BOTTOM
    accent=accent_for_hook(headline,['PIRAMIDA'])
    assert accent == ['PIRAMIDA RAKSASA','LAUT JEPANG',
                      'LEBIH TUA DARI PIRAMIDA MESIR']
    recorded=[]
    original=renderer._draw_word_tracked
    def watch(draw,word,x,y,face,color):
        recorded.append((word,color))
        return original(draw,word,x,y,face,color)
    monkeypatch.setattr(renderer,'_draw_word_tracked',watch)
    src=tmp_path/'source.jpg'
    Image.new('RGB',(1080,1350),'#222a33').save(src)
    renderer.render(src,headline,tmp_path/'reference-layout.jpg',accent_words=['PIRAMIDA'])
    green={w for w,c in recorded if c==renderer.GREEN}
    assert {'PIRAMIDA','RAKSASA','LAUT','JEPANG','LEBIH',
            'TUA','DARI','MESIR'}<=green
    assert ('TERKUBUR',renderer.WHITE) in recorded


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


def test_radio_cluster_headline_has_distributed_semantic_accents():
    title=('Struktur Radio Mirip Simbol Musik Di Ruang Angkasa Ini Ternyata '
           'Lahir Dari Tumbukan Dua Gugus Galaksi')
    groups=accent_for_hook(title,['GALAKSI'])
    assert groups==['STRUKTUR RADIO','SIMBOL MUSIK','GUGUS GALAKSI']
    colored=sum(len(group.split()) for group in groups)
    assert 0.25 <= colored/len(title.split()) <= 0.40
    assert len(groups)<=4


def test_relevant_620px_source_renders_to_final_1080x1350(tmp_path):
    source=tmp_path/'small-relevant.jpg'
    Image.new('RGB',(620,850),'#252637').save(source)
    target=tmp_path/'cover.jpg'
    renderer.render(source,HEADLINE,target)
    assert Image.open(target).size==(1080,1350)


def test_smoke_disaster_green_words_read_as_subject_impact_and_cause():
    headline=('Kota Berpenduduk Dua Juta Jiwa Lumpuh Saat Asap Pekat '
              'Selimuti Hutan Hujan Tropis')
    assert accent_for_hook(headline,['KOTA BERPENDUDUK DUA','ASAP']) == [
        'KOTA','LUMPUH','ASAP PEKAT']
    assert accent_for_hook(headline,[])==['KOTA','LUMPUH','ASAP PEKAT']


def test_meteor_reference_keeps_time_object_and_measured_scale():
    headline=('Malam Ini Bumi Akan Melewati Jejak Komet Yang Pernah '
              'Menghujani Langit Dengan Ratusan Meteor Per Jam')
    assert accent_for_hook(headline,[]) == [
        'MALAM INI','JEJAK KOMET','RATUSAN METEOR PER JAM']


def test_semantic_anchors_are_not_invented_for_unrelated_subject():
    headline='Fisikawan Temukan Sinyal Aneh Dalam Pencarian Partikel Dark Matter'
    accents=accent_for_hook(headline,[])
    assert 'ASAP PEKAT' not in accents and 'LUMPUH' not in accents
    assert 'DARK MATTER' in accents


def test_renderer_white_remains_solid_and_green_is_topmost(tmp_path, monkeypatch):
    headline='Kota Berpenduduk Dua Juta Jiwa Lumpuh Saat Asap Pekat Selimuti Hutan Hujan Tropis'
    image=tmp_path/'image.jpg'
    Image.new('RGB',(1080,1350),'#778899').save(image)
    out=tmp_path/'cover.jpg'
    seen=[]
    original=renderer._draw_word_tracked
    def check(draw,word,x,y,font,color):
        seen.append((word,color))
        return original(draw,word,x,y,font,color)
    monkeypatch.setattr(renderer,'_draw_word_tracked',check)
    renderer.render(image,headline,out,accent_words=['KOTA BERPENDUDUK DUA','ASAP'])
    assert Image.open(out).size==(1080,1350)
    colored={word for word,color in seen if color==renderer.GREEN}
    assert colored=={'KOTA','LUMPUH','ASAP','PEKAT'}
    assert renderer.WHITE=='#FFFFFF'
    assert renderer.GREEN=='#8FFF00'
    assert all(color in (renderer.WHITE,renderer.GREEN) for _,color in seen)
