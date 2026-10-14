"""Regression for four-line cover preflight, repair and protection from repeat downloads."""
from types import SimpleNamespace
from PIL import Image
from sqlalchemy.orm import sessionmaker
from utbot.renderer import cover_fits,require_cover_fit,render
from utbot.hook_editor import cover_fit_alternative
from utbot.models import Base,make_engine,Story,Audit
from utbot.research import fingerprint
from utbot.pipeline import prepare_story,check_evidence,normalize
from utbot.quality_control import assess

GOOD='Fisikawan Temukan Sinyal Aneh Dalam Pencarian Partikel Dark Matter'
TOO_LONG=('Mengapa Para Ilmuwan Menemukan Sinyal Misterius Yang Sangat Tidak Biasa Di Sekitar '
          'Observatorium Kuno Saat Mereka Menyelidiki Anomali Antariksa Yang Belum Dipahami '
          'Secara Mendalam Di Seluruh Dunia')
TEXT=normalize('The telescope took careful observations across several nights. '
               'Scientists must still analyze the results before making claims. ' * 9)
CAPTION=('Para ilmuwan mengamati sesuatu yang tidak biasa dari data pengamatan.\n\n'
         'Temuan ini masih membutuhkan konfirmasi dari pengamatan tambahan.\n\n'
         'Beberapa hasil awal belum cukup untuk menarik kesimpulan.\n\n'
         'Apa yang bisa dipelajari dari pengamatan berikutnya?')
TAGS=['#Astronomi','#NASA','#Sains','#Riset','#UnfoundedTheory']

def data(highlight):
    return {'highlight':highlight,'caption':CAPTION,'hashtags':TAGS,
            'accent_words':['Sinyal'],'image_search':'dark matter telescope',
            'evidence':[{'claim':'observasi','quote':'The telescope took careful observations across several nights.'},
                        {'claim':'hasil perlu diuji','quote':'Scientists must still analyze the results before making claims.'}]}

def test_preflight_matches_render(tmp_path):
    assert cover_fits(GOOD)
    assert not cover_fits(TOO_LONG)
    assert len(require_cover_fit(GOOD))==4
    photo=tmp_path/'source.jpg'
    Image.new('RGB',(1400,1800),'#213547').save(photo)
    try:
        render(photo,TOO_LONG,tmp_path/'bad.jpg')
        assert False,'Four-line layout must reject long headline'
    except ValueError as exc:
        assert 'empat baris' in str(exc)
    assert not (tmp_path/'bad.jpg').exists()
    review=assess(TOO_LONG,CAPTION,TAGS,[{'claim':'1'},{'claim':'2'}])
    assert 'cover_four_line_overflow' in review['issues']

def test_auto_fit_checks_actual_geometry_and_evidence():
    draft=SimpleNamespace(highlight=TOO_LONG,caption=CAPTION,hashtags=TAGS,is_tragedy=False)
    st=SimpleNamespace(title='Astronomy report',
                       evidence=[{'claim':'signal','quote':'The telescope took careful observations across several nights.'},
                                 {'claim':'uncertain','quote':'Scientists must still analyze the results before making claims.'}])
    fixed=cover_fit_alternative(draft,st,llm=lambda _s,_p:{'options':[TOO_LONG,GOOD]})
    assert fixed==GOOD
    assert cover_fits(fixed)

def test_bad_cover_never_triggers_repeated_photo_fetch(monkeypatch):
    engine=make_engine('sqlite://')
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine,expire_on_commit=False)() as db:
        url='https://www.nasa.gov/report'
        story=Story(fingerprint=fingerprint(url),source_url=url,source_name='NASA',
                    title='Astronomy analysis report',topic='astronomy')
        db.add(story);db.flush()
        monkeypatch.setattr('utbot.pipeline.assess',
                            lambda *a,**kw:{'passed':True,'issues':[],'manual_checks':[]})
        monkeypatch.setattr('utbot.pipeline.cover_fit_alternative',
                            lambda *a: (_ for _ in ()).throw(ValueError('no safe choice')))
        calls=[]
        draft=prepare_story(db,story,reader=lambda _url:TEXT,
            writer=lambda s,t:(data(TOO_LONG),check_evidence(data(TOO_LONG),s.source_url,t)),
            image_search=lambda query,limit:calls.append(query),
            image_intake=lambda *args:calls.append('download'))
        assert calls==[]
        assert draft.image_url is None and draft.image_local_path is None
        assert 'empat baris' in draft.last_error
        assert draft.status=='pending_approval'
        qc=db.query(Audit).filter_by(draft_id=draft.id,event='editorial_qc').first()
        assert qc.detail['status']=='needs_manual_review'

def test_old_passed_qc_is_flagged_when_cover_will_not_fit():
    from utbot.models import Draft
    from utbot.quality_control import report_for_draft
    engine=make_engine('sqlite://')
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine,expire_on_commit=False)() as db:
        url='https://nasa.gov/legacy'
        st=Story(fingerprint=fingerprint(url),source_url=url,source_name='NASA',
                 title='Legacy story',topic='astronomy')
        db.add(st);db.flush()
        d=Draft(story_id=st.id,highlight=TOO_LONG,caption=CAPTION,hashtags=TAGS)
        db.add(d);db.flush()
        db.add(Audit(draft_id=d.id,event='editorial_qc',actor='worker',
                     detail={'version':1,'status':'passed_automated',
                             'passed':True,'issues':[],'manual_checks':[]}))
        db.commit()
        report=report_for_draft(db,d,st)
        assert not report['passed']
        assert report['status']=='needs_manual_review'
        assert 'cover_four_line_overflow' in report['issues']

def test_balanced_wrap_can_target_four_lines_even_if_three_would_score_better():
    from PIL import ImageDraw
    from utbot.renderer import _balanced_wrap, _font, WIDTH, MARGIN
    draw=ImageDraw.Draw(Image.new('RGB',(1,1)))
    words='Sebelum Ke Bulan Wahana Ini Harus Lolos Ujian Suhu Ekstrem'.upper().split()
    lines=_balanced_wrap(draw,words,_font(58),WIDTH-2*MARGIN,max_lines=4,exact_lines=4)
    assert len(lines)==4
    assert all(lines)


def test_official_markdown_reaches_author_and_ai_style_qc(monkeypatch):
    from utbot.editorial import read_editorial_guide, editorial_guide_sha256
    from utbot.quality_control import review_style
    from utbot.pipeline import author_from_source
    guide=read_editorial_guide()
    assert '## 2. Aturan Highlight' in guide
    assert '## 3. Aturan Caption' in guide
    assert 'Hook di setiap paragraf' in guide
    assert 'Jari Tanganmu Ternyata Berasal' in guide
    assert '## 9. Checklist Sebelum Publikasi' in guide
    assert len(editorial_guide_sha256())==64
    recorded={}
    def fake_writer(system,payload,**kwargs):
        recorded['system']=system
        return data(GOOD)
    monkeypatch.setattr('utbot.pipeline.generate_json',fake_writer)
    story=SimpleNamespace(title='NASA telescope data',source_url='https://nasa.gov/report',topic='space')
    author_from_source(story,TEXT)
    assert guide in recorded['system']
    captured={}
    def fake_reviewer(system,payload):
        captured['system']=system
        return {'passed':True,'issues':[],'note':'Lolos format SOP'}
    result=review_style(GOOD,CAPTION,[{'claim':'satu','quote':'a quote'},
                                      {'claim':'dua','quote':'another quote'}],llm=fake_reviewer)
    assert result['passed']
    assert guide in captured['system']


def test_lint_follows_latest_markdown_structure():
    from utbot.editorial import lint
    assert 'caption_paragraph_count' in lint(GOOD,
        'Paragraf satu.\\n\\nParagraf dua.\\n\\nPertanyaan?',TAGS)
    assert 'hashtags_embedded_in_caption' in lint(GOOD,CAPTION+' #Sains',TAGS)
    assert 'em_dash' in lint(GOOD+' -- UPDATE',CAPTION,TAGS)
