"""Persisted, owner-controlled editorial automation mode.

Full auto applies only to drafts created after activation. Never backfill
older human-review drafts or bypass versioned QC and image rights.
"""
from sqlalchemy import select
from .models import Audit, Draft, Story
from .editorial import approve, evidence_ready
from .stock_flow import photo_auto_safe
from .config import CONFIG

SETTING_ID='system:editorial_automation'
EVENT='automation_mode_changed'
APPROVAL='approval'
FULL_AUTO='full_auto'


def current_mode(db):
    row=db.execute(select(Audit).where(
        Audit.draft_id==SETTING_ID,Audit.event==EVENT
    ).order_by(Audit.id.desc()).limit(1)).scalar_one_or_none()
    value=(row.detail or {}).get('mode') if row else APPROVAL
    return (value if value in (APPROVAL,FULL_AUTO) else APPROVAL,
            row.created_at if row else None)


def set_mode(db,mode,actor):
    if mode not in (APPROVAL,FULL_AUTO):
        raise ValueError('Mode otomasi tidak valid.')
    db.add(Audit(draft_id=SETTING_ID,event=EVENT,actor=str(actor),
                 detail={'mode':mode}))
    db.commit()
    return mode


def auto_approve_ready(db,limit=15):
    """Only newly generated, independently QC-passed, rights-safe drafts."""
    mode,activated_at=current_mode(db)
    if mode!=FULL_AUTO or not activated_at:
        return {'mode':mode,'approved':[],'blocked':[]}
    from .quality_control import report_for_draft
    if not CONFIG.live_publish or CONFIG.photo_music_mode!='off':
        return {'mode':mode,'approved':[],'blocked':['Instagram photo-only publishing is not enabled']}
    q=select(Draft).where(Draft.status=='pending_approval',
        Draft.publish_state=='unpublished',
        Draft.created_at>=activated_at).order_by(Draft.created_at).limit(limit)
    if db.bind.dialect.name=='postgresql':
        q=q.with_for_update(skip_locked=True)
    rows=db.execute(q).scalars().all()
    approved,blocked=[],[]
    for d in rows:
        story=db.get(Story,d.story_id)
        if not story or story.verification_status!='verified' or not evidence_ready(story):
            blocked.append({'draft_id':d.id,'reason':'source_not_verified'})
            continue
        if not photo_auto_safe(d):
            blocked.append({'draft_id':d.id,'reason':'photo_rights_or_cover_not_verified'})
            continue
        qc=report_for_draft(db,d,story)
        if not qc.get('passed') or qc.get('style_review')!='passed':
            blocked.append({'draft_id':d.id,'reason':'editorial_qc_not_passed'})
            continue
        try:
            approve(db,d,'system:full_auto')
        except (ValueError,RuntimeError):
            blocked.append({'draft_id':d.id,'reason':'approval_safety_gate'})
            continue
        # Mark reviewed only after strict public-domain/CC0 photo policy passes.
        d.rights_reviewed=True
        db.add(Audit(draft_id=d.id,event='photo_only_approved',
                     actor='system:full_auto',detail={'version':d.version,
                     'mode':'full_auto','automatically_generated':True}))
        db.add(Audit(draft_id=d.id,event='full_auto_approved',
                     actor='system:full_auto',detail={'version':d.version}))
        approved.append(d.id)
    db.commit()
    return {'mode':mode,'approved':approved,'blocked':blocked}
