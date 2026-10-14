"""The user-supplied newsroom SOP must stay authoritative in every AI workflow."""
from types import SimpleNamespace
from utbot.editorial import read_editorial_guide, editorial_instructions
from utbot.pipeline import author_from_source, normalize
from utbot.rewrite import rewrite
from utbot.quality_control import review_style, assess

TEXT = normalize(
    ('Scientists studied observations from a distant telescope array. '
     'They said additional measurements are required before any discovery claim. ') * 10
)

def test_attached_markdown_is_authoritative():
    guide = read_editorial_guide()
    assert guide.startswith('# Panduan Penulisan Berita Unfounded Theory')
    for phrase in ('## 4. Toolkit Hook','## 6. Berita Bencana dan Tragedi Nyata',
                   '## 8. Catatan Visual Carousel','## 9. Checklist Sebelum Publikasi',
                   'Jari Tanganmu Ternyata Berasal'):
        assert phrase in guide
    assert guide in editorial_instructions()

def test_retry_feedback_is_included_without_changing_evidence():
    story = SimpleNamespace(title='Telescope report', source_url='https://nasa.gov/report', topic='astronomy')
    recorded = {}
    def model(query):
        import json
        recorded.update(json.loads(query))
        return {
            'highlight': 'Fisikawan Temukan Sinyal Aneh Dalam Pencarian Partikel Dark Matter',
            'caption': 'Sebuah pengamatan menyimpan kejutan baru.\n\nPara ilmuwan mencatat data unik.\n\nNamun hasil awal belum final.\n\nApa yang perlu diuji selanjutnya?',
            'hashtags':['#Sains','#Fisika','#Astronomi','#Riset','#UnfoundedTheory'],
            'evidence':[
                {'claim':'pengamatan', 'quote':'Scientists studied observations from a distant telescope array.'},
                {'claim':'belum penemuan', 'quote':'They said additional measurements are required before any discovery claim.'}
            ],
        }
    author_from_source(story,TEXT,llm=model,revision_feedback={'issues':['caption_opening_too_flat']})
    assert recorded['revision_feedback']['issues']==['caption_opening_too_flat']
    assert recorded['source_text']==TEXT

def test_rewrite_and_style_review_receive_user_sop(monkeypatch):
    recorded={}
    def fake_generate(system,data,**kwargs):
        recorded['system']=system
        return {'text':'Revisi singkat sesuai bukti.'}
    monkeypatch.setattr('utbot.rewrite.generate_json',fake_generate)
    draft=SimpleNamespace(highlight='Fisikawan Temukan Sinyal Aneh Dalam Pencarian Partikel Dark Matter',
                          caption='Awal.\n\nFakta.\n\nNamun.\n\nMengapa?',
                          hashtags=['#Sains','#NASA','#Astronomi','#Riset','#UnfoundedTheory'])
    story=SimpleNamespace(title='Sains',evidence=[{'claim':'x','quote':'fakta resmi'}])
    assert rewrite('caption','perbaiki awal',draft,story)=='Revisi singkat sesuai bukti.'
    assert 'Toolkit Hook' in recorded['system']
    result=review_style(draft.highlight,draft.caption,
                        [{'claim':'satu','quote':'a'}, {'claim':'dua','quote':'b'}],
                        llm=lambda system,data:({'passed':True,'issues':[],'note':'Lolos SOP lengkap','checks':{
        'curiosity_gap':{'passed':True,'reason':'Sumber sinyal aneh tetap belum dijawab oleh headline','unanswered_question':'Dari manakah sinyal aneh itu benar-benar berasal?'},
        'reader_relevance':{'passed':True,'reason':'Sinyal aneh membuka pertanyaan penelitian sains baru'},
        'caption_story':{'passed':True,'reason':'Caption memiliki alur pengamatan, pivot dan penutup yang relevan'},
        'fact_integrity':{'passed':True,'reason':'Tidak ada angka atau temuan pasti di luar kutipan'}}}
                            if 'Hook di setiap paragraf' in system else {'passed':False,'issues':['missing_sop']}))
    assert result['passed']
