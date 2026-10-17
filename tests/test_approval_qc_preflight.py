"""Regression tests for one-click Telegram Approve and independent QC repair.

All Gemini requests are mocked: no external API calls or paid services.
"""
from dataclasses import replace
from datetime import datetime, timezone
from sqlalchemy.orm import sessionmaker
from utbot.models import Base, make_engine, Story, Draft, Audit
from utbot.editorial import editorial_guide_sha256, revise
from utbot.quality_control import QC_RUBRIC_VERSION
from utbot.approval_flow import preflight_approval
from utbot import web
import pytest
import httpx


@pytest.fixture
def db():
    engine = make_engine('sqlite://')
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine,expire_on_commit=False)() as session:
        yield session


class FakeBot:
    def __init__(self):
        self.sent = []
        self.answered = []
    def message(self, chat_id, text, buttons=None):
        self.sent.append(text)
    def answer(self, callback_id, text):
        self.answered.append(text)


def seed(db):
    src='https://science.nasa.gov/universe/'
    story=Story(title='Unexpected giant X-ray structure in space',
                source_url=src,source_name='NASA',topic='astronomy',
                fingerprint='a'*64,verification_status='verified',
                evidence=[
                    {'claim':'Observation found','url':src,
                     'quote':'The telescope saw a structure.',
                     'evidence_checked':True},
                    {'claim':'Further research required','url':src,
                     'quote':'Further analysis is still required.',
                     'evidence_checked':True},
                ])
    db.add(story);db.flush()
    draft=Draft(story_id=story.id,highlight=(
        'Inilah Tangan Tuhan, Struktur Sinar-X Raksasa Yang Masih Membingungkan NASA'),
        caption=('Para peneliti memeriksa struktur sinar-X di angkasa.\n\n'
                 'NASA menjelaskan temuan tersebut berdasarkan pengamatan.\n\n'
                 'Namun, proses penelitian masih terus berlangsung.\n\n'
                 'Apa yang akan ditemukan dari struktur ini selanjutnya?'),
        hashtags=['#NASA','#Astronomi','#Sains','#Antariksa','#UnfoundedTheory'],
        image_url='https://example.org/cover-final.jpg',
        status='pending_approval',publish_state='unpublished')
    db.add(draft);db.commit()
    return story,draft


def callback(draft,action='approve',user_id=42):
    return {'callback_query':{
        'id':'callback-123','from':{'id':user_id},
        'message':{'chat':{'id':100}},
        'data':f'{action}:{draft.id}:{draft.version}',
    }}


def configure(monkeypatch):
    bot=FakeBot()
    monkeypatch.setattr(web,'_bot',lambda:bot)
    monkeypatch.setattr(web,'CONFIG',replace(web.CONFIG,admin_ids=frozenset({42}),daily_limit=2))
    return bot


def passing_style(*args, **kwargs):
    return {'passed':True,'issues':[],
            'checks':{
                'curiosity_gap':{'passed':True,'reason':'Hook menyisakan pertanyaan yang relevan dan spesifik.',
                                 'unanswered_question':'Mengapa bentuk sinar-X menyerupai tangan?'},
                'reader_relevance':{'passed':True,'reason':'Peristiwa mudah dikaitkan dengan pengamatan manusia.'},
                'caption_story':{'passed':True,'reason':'Empat paragraf mengalir dari pengamatan ke pertanyaan.'},
                'fact_integrity':{'passed':True,'reason':'Pernyataan didukung kutipan sumber primer.'},
            }, 'rubric_version':QC_RUBRIC_VERSION,'note':'QC independent completed'}


def failed_style(*args, **kwargs):
    result=passing_style()
    result['passed']=False
    result['issues']=['qc_curiosity_gap']
    result['checks']['curiosity_gap']['passed']=False
    result['checks']['curiosity_gap']['reason']='Judul sudah menjelaskan hasil dan belum menyisakan rasa penasaran.'
    return result


def audit(db,draft,detail=None):
    data=detail or {
        'version':draft.version,'status':'needs_manual_review','passed':False,
        'issues':['independent_style_qc_not_recorded'],
        'style_review':'failed','rubric_version':QC_RUBRIC_VERSION,
        'guide_sha256':editorial_guide_sha256(),
    }
    db.add(Audit(draft_id=draft.id,event='editorial_qc',actor='worker',detail=data))
    db.commit()


def all_qc(db,draft):
    return db.query(Audit).filter_by(draft_id=draft.id,event='editorial_qc').order_by(Audit.id).all()


def test_old_unrecorded_style_is_automatically_rechecked_and_scheduled(db,monkeypatch):
    story,draft=seed(db)
    audit(db,draft)
    bot=configure(monkeypatch)
    called=[]
    monkeypatch.setattr('utbot.quality_control.review_style',
                        lambda *args,**kwargs: (called.append(1) or passing_style()))
    out=web.telegram_webhook(callback(draft),db=db)
    assert out['ok']
    assert draft.status=='approved' and draft.approved_version==draft.version
    assert draft.scheduled_at is not None
    assert len(called)==1
    assert len(all_qc(db,draft))==2
    assert all_qc(db,draft)[-1].detail['trigger']=='telegram_approve'
    assert all_qc(db,draft)[-1].detail['passed']
    assert any('Disetujui setelah QC' in s for s in bot.sent)
    assert any('Menu utama' in s for s in bot.sent)

    original_time=draft.scheduled_at
    repeated=web.telegram_webhook(callback(draft),db=db)
    assert repeated['approval']=='already_approved'
    assert draft.scheduled_at==original_time
    assert len(called)==1


def test_valid_cached_qc_does_not_call_ai(db,monkeypatch):
    _,draft=seed(db)
    passing=passing_style()
    audit(db,draft,{
        'version':draft.version,'passed':True,'status':'passed_automated',
        'issues':[],'style_review':'passed','checks':passing['checks'],
        'rubric_version':QC_RUBRIC_VERSION,
        'guide_sha256':editorial_guide_sha256(),
    })
    configure(monkeypatch)
    def must_not_call(*args,**kwargs):
        raise AssertionError('valid cached QC should not call AI')
    monkeypatch.setattr('utbot.quality_control.review_style',must_not_call)
    out=web.telegram_webhook(callback(draft),db=db)
    assert out['ok'] and draft.status=='approved'
    assert len(all_qc(db,draft))==1


def test_failed_curiosity_gap_without_repair_remains_unapproved(db,monkeypatch):
    _,draft=seed(db)
    audit(db,draft)
    bot=configure(monkeypatch)
    called=[]
    monkeypatch.setattr('utbot.quality_control.review_style',
                        lambda *args,**kwargs:(called.append(1) or failed_style()))
    monkeypatch.setattr('utbot.approval_flow.auto_repair_rejected_caption',lambda *a,**k:None)
    first=web.telegram_webhook(callback(draft),db=db)
    assert first['approval']=='qc_not_passed'
    assert draft.status=='pending_approval' and draft.scheduled_at is None
    assert len(all_qc(db,draft))==2 and len(called)==1
    assert any('rasa penasaran' in s for s in bot.sent)
    second=web.telegram_webhook(callback(draft),db=db)
    assert second['approval']=='qc_not_passed'
    assert len(called)==1  # bounded on free Gemini quota
    assert len(all_qc(db,draft))==2


def test_unavailable_ai_keeps_failed_qc_audit_and_does_not_schedule(db,monkeypatch):
    _,draft=seed(db)
    audit(db,draft)
    bot=configure(monkeypatch)
    called=[]
    def unavailable(*args,**kwargs):
        called.append(1)
        raise httpx.ReadTimeout('temporary timeout')
    monkeypatch.setattr('utbot.quality_control.review_style',unavailable)
    first=web.telegram_webhook(callback(draft),db=db)
    assert first['approval']=='qc_not_passed'
    assert draft.status=='pending_approval'
    assert len(all_qc(db,draft))==2
    assert 'independent_style_qc_unavailable' in all_qc(db,draft)[-1].detail['issues']
    assert any('Pemeriksaan AI belum tersedia' in s for s in bot.sent)
    web.telegram_webhook(callback(draft),db=db)
    assert len(called)==1


def test_automatically_generated_draft_with_missing_qc_is_recovered(db,monkeypatch):
    _,draft=seed(db)
    db.add(Audit(draft_id=draft.id,event='primary_quotes_checked',actor='worker',
                 detail={'claim_count':2}))
    db.commit()
    configure(monkeypatch)
    monkeypatch.setattr('utbot.quality_control.review_style',passing_style)
    assert web.telegram_webhook(callback(draft),db=db)['ok']
    assert draft.status=='approved'
    assert len(all_qc(db,draft))==1
    assert all_qc(db,draft)[0].detail['passed']


def test_revised_draft_version_forces_fresh_qc(db,monkeypatch):
    _,draft=seed(db)
    passing=passing_style()
    audit(db,draft,{
        'version':1,'passed':True,'status':'passed_automated','issues':[],
        'style_review':'passed','checks':passing['checks'],
        'rubric_version':QC_RUBRIC_VERSION,'guide_sha256':editorial_guide_sha256(),
    })
    revise(db,draft,'caption',draft.caption.replace('proses penelitian','penelitian ilmiah'),'42')
    db.commit()
    configure(monkeypatch)
    monkeypatch.setattr('utbot.quality_control.review_style',passing_style)
    assert web.telegram_webhook(callback(draft),db=db)['ok']
    assert draft.status=='approved'
    assert len(all_qc(db,draft))==2
    assert all_qc(db,draft)[-1].detail['version']==2


def test_failing_story_facts_do_not_trigger_ai_and_never_schedule(db,monkeypatch):
    story,draft=seed(db)
    story.verification_status='needs_fact_check'
    audit(db,draft)
    configure(monkeypatch)
    monkeypatch.setattr('utbot.quality_control.review_style',
                        lambda *a,**k:(_ for _ in ()).throw(AssertionError('AI must not run')))
    assert web.telegram_webhook(callback(draft),db=db)['ok']
    assert draft.status=='pending_approval'
    assert len(all_qc(db,draft))==1


def test_manual_import_without_automated_audit_keeps_single_human_review(db,monkeypatch):
    _,draft=seed(db)
    configure(monkeypatch)
    monkeypatch.setattr('utbot.quality_control.review_style',
                        lambda *a,**k:(_ for _ in ()).throw(AssertionError('AI must not run')))
    assert preflight_approval(db,draft,db.get(Story,draft.story_id)) is None
    assert web.telegram_webhook(callback(draft),db=db)['ok']
    assert draft.status=='approved'


def test_photo_only_approval_posts_only_the_approved_draft(db,monkeypatch):
    _,draft=seed(db)
    audit(db,draft)
    bot=configure(monkeypatch)
    monkeypatch.setattr(web,'CONFIG',replace(web.CONFIG,photo_music_mode='off',live_publish=True))
    monkeypatch.setattr('utbot.quality_control.review_style',passing_style)
    calls=[]
    def fake_publish(*,db,target_draft_id):
        calls.append(target_draft_id)
        return {'published':[target_draft_id],'instagram_media_id':'1789000000000'}
    monkeypatch.setattr(web,'publish_job',fake_publish)
    result=web.telegram_webhook(callback(draft),db=db)
    assert result['approval']=='approved_for_instagram'
    assert draft.status=='approved' and draft.scheduled_at is not None
    assert calls==[draft.id]
    assert any('Instagram mengonfirmasi' in msg for msg in bot.sent)
    repeated=web.telegram_webhook(callback(draft),db=db)
    assert repeated['approval']=='already_approved'
    assert calls==[draft.id]


def test_photo_only_approval_never_claims_publish_when_gate_disabled(db,monkeypatch):
    _,draft=seed(db)
    audit(db,draft)
    bot=configure(monkeypatch)
    monkeypatch.setattr(web,'CONFIG',replace(web.CONFIG,photo_music_mode='off',live_publish=False))
    monkeypatch.setattr('utbot.quality_control.review_style',passing_style)
    monkeypatch.setattr(web,'publish_job',lambda **kwargs: (_ for _ in ()).throw(
        AssertionError('Never publish when live flag is disabled')))
    result=web.telegram_webhook(callback(draft),db=db)
    assert result['approval']=='approved_for_instagram'
    assert draft.status=='approved'
    assert any('belum aktif' in msg for msg in bot.sent)
    assert not any('mengonfirmasi foto sudah terbit' in msg for msg in bot.sent)


def test_photo_only_approval_reports_missing_prerequisite(db,monkeypatch):
    from fastapi import HTTPException
    _,draft=seed(db)
    audit(db,draft)
    bot=configure(monkeypatch)
    monkeypatch.setattr(web,'CONFIG',replace(web.CONFIG,photo_music_mode='off',live_publish=True))
    monkeypatch.setattr('utbot.quality_control.review_style',passing_style)
    monkeypatch.setattr(web,'publish_job',lambda **kwargs: (_ for _ in ()).throw(
        HTTPException(status_code=503,detail='Logo resmi belum dikonfigurasi')))
    out=web.telegram_webhook(callback(draft),db=db)
    assert out['approval']=='approved_for_instagram'
    assert draft.status=='approved' and draft.publish_state=='unpublished'
    assert any('belum dapat diposting' in msg for msg in bot.sent)


def test_live_photo_approval_without_credit_is_allowed(db,monkeypatch):
    _,draft=seed(db)
    bot=configure(monkeypatch)
    monkeypatch.setattr(web,'CONFIG',replace(web.CONFIG,photo_music_mode='off',live_publish=True))
    monkeypatch.setattr(web,'publish_job',lambda **kwargs: {'waiting':draft.id})
    result=web.telegram_webhook(callback(draft),db=db)
    assert result['approval']=='approved_for_instagram'
    assert draft.status=='approved' and draft.rights_reviewed
    assert any('sedang diproses Instagram' in msg for msg in bot.sent)


def test_live_photo_approval_reports_actual_blocker_not_draft_uuid(db,monkeypatch):
    _,draft=seed(db)
    draft.image_credit='NASA/Hubble Mission'
    draft.photo_license='Public Domain'
    db.commit()
    bot=configure(monkeypatch)
    monkeypatch.setattr(web,'CONFIG',replace(web.CONFIG,photo_music_mode='off',live_publish=True))
    monkeypatch.setattr(web,'publish_job',lambda **kwargs:
                        {'blocked':draft.id,'error':'Hak foto belum dikonfirmasi'})
    result=web.telegram_webhook(callback(draft),db=db)
    assert result['approval']=='approved_for_instagram'
    assert any('Alasan: Hak foto belum dikonfirmasi' in msg for msg in bot.sent)
    assert not any('Status: '+draft.id in msg for msg in bot.sent)


def test_approve_repairs_curiosity_gap_then_requires_owner_to_confirm(db,monkeypatch):
    story,draft=seed(db)
    audit(db,draft,{
        'version':draft.version,'status':'needs_manual_review','passed':False,
        'issues':['qc_curiosity_gap'],'style_review':'rejected',
        'checks':failed_style()['checks'],
        'rubric_version':QC_RUBRIC_VERSION,
        'guide_sha256':editorial_guide_sha256()})
    bot=configure(monkeypatch)
    old_caption=draft.caption
    replacement=old_caption.replace('Para peneliti memeriksa struktur sinar-X di angkasa.',
                                    'Di langit yang gelap, teleskop melihat pola yang belum terjelaskan.')
    monkeypatch.setattr('utbot.rewrite.rewrite',lambda *args,**kwargs:replacement)
    monkeypatch.setattr('utbot.quality_control.review_style',passing_style)
    previews=[]
    monkeypatch.setattr(web,'send_preview',lambda *args:previews.append(1))
    result=web.telegram_webhook(callback(draft),db=db)
    assert result['approval']=='auto_revised_needs_confirmation'
    assert draft.status=='pending_approval'
    assert draft.version==2
    assert draft.caption==replacement
    assert draft.scheduled_at is None
    assert previews==[1]
    assert all_qc(db,draft)[-1].detail['passed']
    assert 'tekan Approve sekali lagi' in bot.sent[-1]
    second=web.telegram_webhook(callback(draft),db=db)
    assert second['ok'] and draft.status=='approved'


def test_auto_repair_does_not_override_failed_independent_qc(db,monkeypatch):
    story,draft=seed(db)
    audit(db,draft,{
        'version':1,'passed':False,'issues':['qc_curiosity_gap'],
        'style_review':'rejected','checks':failed_style()['checks'],
        'rubric_version':QC_RUBRIC_VERSION,
        'guide_sha256':editorial_guide_sha256()})
    configure(monkeypatch)
    monkeypatch.setattr('utbot.rewrite.rewrite',lambda *a,**k:
                        draft.caption.replace('Para peneliti memeriksa',
                                              'Sejumlah peneliti mengamati'))
    monkeypatch.setattr('utbot.quality_control.review_style',failed_style)
    result=web.telegram_webhook(callback(draft),db=db)
    assert result['approval']=='qc_not_passed'
    assert draft.status=='pending_approval'
    assert draft.scheduled_at is None


def test_failed_repair_keeps_original_version_and_records_diagnostic(db,monkeypatch):
    story,draft=seed(db)
    from utbot.approval_flow import auto_repair_rejected_caption
    before=draft.caption
    monkeypatch.setattr('utbot.rewrite.rewrite',lambda *a,**k:before)
    result=auto_repair_rejected_caption(db,draft,story,
        {'issues':['qc_curiosity_gap'],'checks':failed_style()['checks']},
        actor='42',max_attempts=2)
    assert result is None
    assert draft.caption==before
    assert draft.version==1
    record=db.query(Audit).filter_by(draft_id=draft.id,
            event='approval_caption_repair_failed').first()
    assert record.detail['reason']=='unchanged_caption'


def test_repair_can_retry_after_bad_first_candidate(db,monkeypatch):
    story,draft=seed(db)
    from utbot.approval_flow import auto_repair_rejected_caption
    original=draft.caption
    good=original.replace('Para peneliti memeriksa struktur sinar-X di angkasa.',
                          'Di ruang angkasa, pengamatan baru membuka teka-teki besar.')
    calls=[]
    def fake_rewrite(*a,**k):
        calls.append(1)
        return 'Invalid' if len(calls)==1 else good
    monkeypatch.setattr('utbot.rewrite.rewrite',fake_rewrite)
    monkeypatch.setattr('utbot.quality_control.review_style',passing_style)
    result=auto_repair_rejected_caption(db,draft,story,
        {'issues':['qc_curiosity_gap'],'checks':failed_style()['checks']},
        actor='42',max_attempts=3)
    assert result and result['passed']
    assert len(calls)==2
    assert draft.version==2 and draft.caption==good
    assert draft.status=='pending_approval'


def test_normalize_caption_format_removes_inline_hashtags_and_splits_lines():
    from utbot.rewrite import normalize_caption_format
    raw=('Pembuka misteri.\\nNama objek diungkap kemudian.\\n'
         'Bukti utama disampaikan.\\nApa yang akan diperiksa berikutnya?\\n'
         '#NASA #Sains #Astronomi')
    result=normalize_caption_format(raw)
    assert result.count('\\n\\n')==3
    assert result.endswith('?')
    assert '#NASA' not in result
    assert '#Sains' not in result


def test_repair_retries_with_specific_deterministic_feedback(db,monkeypatch):
    story,draft=seed(db)
    from utbot.approval_flow import auto_repair_rejected_caption
    old=draft.caption
    fixed=old.replace('Para peneliti memeriksa struktur sinar-X di angkasa.',
                      'Di angkasa, teleskop merekam pola yang belum terjelaskan.')
    calls=[]
    def fake_rewrite(field,instruction,*args):
        calls.append(instruction)
        if len(calls)==1:
            return 'Satu paragraf tanpa pertanyaan #NASA'
        return fixed+'\\n#NASA #Astronomi'
    monkeypatch.setattr('utbot.rewrite.rewrite',fake_rewrite)
    monkeypatch.setattr('utbot.quality_control.review_style',passing_style)
    result=auto_repair_rejected_caption(
        db,draft,story,{'issues':['qc_curiosity_gap'],
        'checks':failed_style()['checks']},actor='42',max_attempts=3)
    assert result and result['passed']
    assert len(calls)==2
    assert 'caption_paragraph_count' in calls[1]
    assert 'ending_not_question' in calls[1]
    assert draft.version==2
    assert '#NASA' not in draft.caption
