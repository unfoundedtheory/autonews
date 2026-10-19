"""Guard lossless AI caption cleanup and strict editorial validation."""
from types import SimpleNamespace
import pytest
from utbot.caption_format import normalize_generated_caption, DraftFormatError
from utbot.pipeline import author_from_source, normalize
from utbot.editorial import lint

def test_single_line_breaks_restore_four_paragraphs_and_move_footer():
    raw=('Caption: Sebuah teleskop merekam cahaya yang tak biasa.\n'
         'Peneliti NASA menganalisis pengamatan terbaru.\n'
         'Namun data awal belum membuktikan penyebabnya.\n'
         'Bagaimana para ilmuwan akan memastikannya?\n\n'
         'Photo by : NASA\n#NASA #Sains #Langit #Riset #UnfoundedTheory')
    caption,tags,repairs=normalize_generated_caption(raw)
    assert caption.count('\n\n')==3
    assert caption.endswith('?')
    assert 'Photo by' not in caption and '#' not in caption
    assert len(tags)==5
    assert 'restored_paragraph_separators' in repairs
    assert not lint('Para Peneliti Melihat Sinyal Tak Biasa Dalam Pengamatan Teleskop',
                    caption,tags)

def test_factual_assertion_never_transformed_into_question():
    original='Hasil pemeriksaan masih sementara.\n\nKlaim tersebut belum pasti.'
    caption,_,_=normalize_generated_caption(original)
    assert caption==original
    assert not caption.endswith('?')

def test_bad_format_emits_specific_codes_without_passing_qc():
    st=SimpleNamespace(title='Observasi teleskop',
                       source_url='https://science.nasa.gov/research',
                       published_at=None,topic='astronomy')
    text=normalize(('Scientists studied observations from a distant telescope array. '
                    'They said additional measurements are required before any discovery claim. ')*8)
    def bad(_):
        return {'highlight':'Para Peneliti Menyelidiki Sinyal Aneh Dari Teleskop Jauh',
                'caption':'Satu kalimat saja, bukan empat paragraf.',
                'hashtags':['#Sains','#NASA','#Riset','#Data','#UnfoundedTheory'],
                'evidence':[{'claim':'pengamatan','quote':'Scientists studied observations from a distant telescope array.'},
                            {'claim':'pengujian','quote':'They said additional measurements are required before any discovery claim.'}]}
    with pytest.raises(DraftFormatError) as e:
        author_from_source(st,text,llm=bad)
    assert 'caption_paragraph_count' in e.value.issue_codes
