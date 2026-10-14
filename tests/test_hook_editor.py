"""Human-controlled hook suggestions based on evidence and safe revision."""
from types import SimpleNamespace
from utbot.hook_editor import alternatives
from utbot.quality_control import assess

def make_draft():
    return SimpleNamespace(
        highlight='Fisikawan Temukan Sinyal Aneh Dalam Pencarian Partikel Dark Matter',
        caption=('Para ilmuwan menemukan petunjuk baru dalam data pengamatan.\n\n'
                 'Temuan itu belum cukup untuk menjadi bukti.\n\n'
                 'Namun, pengujian tambahan dibutuhkan untuk memperkuat hasilnya.\n\n'
                 'Apa yang akan terungkap pada analisis berikutnya?'),
        hashtags=['#Sains','#Fisika','#Astronomi','#Riset','#UnfoundedTheory'],
        is_tragedy=False)
def make_story():
    return SimpleNamespace(title='New indications in dark matter experiment',evidence=[
        {'claim':'Petunjuk baru','quote':'New data raises questions about dark matter signals.'},
        {'claim':'Belum pasti','quote':'The team stressed that more measurements were needed.'}])

def test_alternatives_selects_three_and_blocks_unsupported_number():
    response={'options':[
        'Mengapa Sinyal Aneh Ini Membuat Fisikawan Meninjau Kembali Pencarian Dark Matter?',
        'Dari Data Baru Muncul Pertanyaan Besar Tentang Partikel Yang Belum Terlihat',
        'Sinyal Yang Belum Pasti Ini Bisa Mengubah Cara Ilmuwan Mencari Dark Matter',
        'Peneliti Membuktikan 99 Persen Dark Matter Berasal Dari Matahari']}
    items=alternatives(make_draft(),make_story(),llm=lambda *_:response)
    assert len(items)==3
    assert all('99' not in x for x in items)

def test_bland_mission_lead_fails_editorial_qc():
    draft=make_draft()
    review=assess('Misi Smile Akan Mempelajari Angin Matahari Dan Medan Magnet Bumi',
                  draft.caption,draft.hashtags,make_story().evidence)
    assert not review['passed']
    assert 'hook_factual_summary_not_curiosity_gap' in review['issues']


def test_mars_year_summary_does_not_pass_curiosity_gap():
    title='Mengapa Satu Tahun Penuh di Planet Merah Berlangsung Selama Hampir Dua Kali Lipat Waktu Bumi'
    d=make_draft()
    result=assess(title,d.caption,d.hashtags,make_story().evidence,check_cover=False)
    assert not result['passed']
    assert 'hook_explains_answer_in_title' in result['issues']


def test_shallow_independent_qc_is_not_a_pass():
    import pytest
    from utbot.quality_control import review_style
    d=make_draft()
    with pytest.raises(ValueError,match='rubrik'):
        review_style(d.highlight,d.caption,make_story().evidence,
                     llm=lambda *_:{'passed':True,'issues':[]})
