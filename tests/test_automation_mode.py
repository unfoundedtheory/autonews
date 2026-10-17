"""Regression tests for explicit Telegram full-auto opt-in and safe draft gating."""
from dataclasses import replace
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from utbot import web
from utbot.automation_mode import current_mode,set_mode,auto_approve_ready
from utbot.models import Story,Draft,Audit
from tests.test_telegram_production_menu import session,FakeTelegram,update


def test_automation_mode_defaults_to_approval_and_persists():
    db=session()
    try:
        assert current_mode(db)[0]=='approval'
        set_mode(db,'full_auto',42)
        assert current_mode(db)[0]=='full_auto'
        set_mode(db,'approval',42)
        assert current_mode(db)[0]=='approval'
    finally:
        db.close()


def test_status_switch_requires_confirmation(monkeypatch):
    db=session()
    bot=FakeTelegram()
    monkeypatch.setattr(web,'_bot',lambda:bot)
    monkeypatch.setattr(web,'CONFIG',replace(web.CONFIG,admin_ids=frozenset({42}),
        live_publish=True,photo_music_mode='off'))
    try:
        web.telegram_webhook(update('status'),db=db)
        assert 'DENGAN APPROVAL' in bot.messages[-1][0]
        assert 'nav:mode:full_auto' in str(bot.messages[-1][1])
        response=web.telegram_webhook(update('mode:full_auto'),db=db)
        assert response['automation_mode']=='confirmation_required'
        assert current_mode(db)[0]=='approval'
        response=web.telegram_webhook(update('mode_confirm:full_auto'),db=db)
        assert response['automation_mode']=='full_auto'
        assert current_mode(db)[0]=='full_auto'
        web.telegram_webhook(update('status'),db=db)
        assert 'FULL OTOMATIS' in bot.messages[-1][0]
        response=web.telegram_webhook(update('mode:approval'),db=db)
        assert response['automation_mode']=='approval'
        assert current_mode(db)[0]=='approval'
    finally:
        db.close()


def test_full_auto_never_approves_old_or_unverified_drafts(monkeypatch):
    db=session()
    monkeypatch.setattr('utbot.automation_mode.CONFIG',
        replace(web.CONFIG,live_publish=True,photo_music_mode='off'))
    try:
        from utbot.research import fingerprint
        url='https://science.nasa.gov/full-auto-test'
        story=Story(fingerprint=fingerprint(url),title='Test',
                    source_url=url,source_name='NASA',topic='space',
                    verification_status='needs_fact_check')
        db.add(story);db.flush()
        old=Draft(story_id=story.id,highlight='Test',caption='Test',hashtags=[],
                  created_at=datetime.now(timezone.utc)-timedelta(days=2))
        db.add(old);db.commit()
        set_mode(db,'full_auto',42)
        result=auto_approve_ready(db)
        assert result['approved']==[]
        assert old.status=='pending_approval'
    finally:
        db.close()


def test_full_auto_approves_only_new_qc_passed_rights_safe_draft(monkeypatch):
    db=session()
    monkeypatch.setattr('utbot.automation_mode.CONFIG',
        replace(web.CONFIG,live_publish=True,photo_music_mode='off'))
    try:
        from utbot.research import fingerprint
        url='https://science.nasa.gov/full-auto-safe-test'
        story=Story(fingerprint=fingerprint(url),title='NASA Science',
            source_url=url,source_name='NASA',topic='space',
            verification_status='verified',
            evidence=[{'claim':'Evidence one','url':url,'evidence_checked':True},
                      {'claim':'Evidence two','url':url,'evidence_checked':True}])
        db.add(story);db.commit()
        set_mode(db,'full_auto',42)
        draft=Draft(story_id=story.id,highlight='A verified astronomical finding',
            caption='Verified text',hashtags=[],
            image_url='https://example.org/verified-cover.jpg')
        db.add(draft);db.commit()
        monkeypatch.setattr('utbot.automation_mode.photo_auto_safe',
                            lambda d: True)
        monkeypatch.setattr('utbot.quality_control.report_for_draft',
                            lambda *args:{'passed':True,'style_review':'passed'})
        outcome=auto_approve_ready(db)
        assert outcome['approved']==[draft.id]
        assert draft.status=='approved'
        assert draft.approved_version==draft.version
        assert draft.rights_reviewed is True
        events=db.query(Audit).filter(Audit.draft_id==draft.id).all()
        assert any(e.event=='photo_only_approved' and
                   e.detail.get('version')==draft.version for e in events)
        assert auto_approve_ready(db)['approved']==[]
    finally:
        db.close()
