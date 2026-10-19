"""Versioned, owner-intended automatic photo posts from the Content Studio calendar.

The website never skips editorial QC or image rights, and never touches old
manual-with-music approvals. The owner explicitly chooses a fixed WIB slot.
"""
from datetime import datetime, timezone
from sqlalchemy import select, text
from .scheduler import WIB, SLOTS
from .models import Draft, Story, Audit
from .editorial import approve, evidence_ready
from .stock_flow import photo_auto_safe
from .quality_control import report_for_draft
from .config import CONFIG


def _events(db, draft, event):
    return db.execute(select(Audit.detail).where(
        Audit.draft_id==draft.id, Audit.event==event
    ).order_by(Audit.id.desc())).scalars().all()


def planner_photo_only(db, draft):
    """An immutable consent tied to the current approved content version."""
    consent=any((d or {}).get('version')==draft.version and
                (d or {}).get('source')=='content_studio' for d in
                _events(db,draft,'photo_only_approved'))
    recent=db.execute(select(Audit.detail).where(
        Audit.draft_id==draft.id,Audit.event=='content_plan_changed'
    ).order_by(Audit.id.desc()).limit(1)).scalar_one_or_none()
    return bool(consent and recent and recent.get('auto_publish') is True
                and recent.get('version')==draft.version)


def pinned_planner_schedule(db, draft):
    if (draft.status!='approved' or draft.approved_version!=draft.version or
        draft.publish_state!='unpublished' or not planner_photo_only(db,draft)):
        return False
    recent=db.execute(select(Audit.detail).where(
        Audit.draft_id==draft.id,Audit.event=='content_plan_changed'
    ).order_by(Audit.id.desc()).limit(1)).scalar_one_or_none()
    return bool(recent and recent.get('version')==draft.version and
                recent.get('auto_publish') is True and
                recent.get('planned_at') and draft.scheduled_at)


def _validate_slot(at):
    if at is None or at.tzinfo is None:
        raise ValueError('Jadwal posting harus menyertakan zona waktu WIB.')
    utc=at.astimezone(timezone.utc)
    local=utc.astimezone(WIB)
    if local.hour not in SLOTS or (local.minute,local.second,local.microsecond)!=(0,0,0):
        raise ValueError('Posting otomatis hanya pada pukul 06.00, 12.00, atau 18.00 WIB.')
    if utc<=datetime.now(timezone.utc):
        raise ValueError('Jadwal posting harus di masa depan.')
    return utc


def schedule_web_post(db, draft, when, *, actor='web_content_studio'):
    if not CONFIG.live_publish:
        raise ValueError('ENABLE_LIVE_PUBLISH belum aktif. Jadwal otomatis belum dapat disimpan.')
    utc=_validate_slot(when)
    if db.bind.dialect.name=='postgresql':
        db.execute(text('SELECT pg_advisory_xact_lock(917540134)'))
    if draft.status in ('published','rejected') or draft.publish_state!='unpublished':
        raise ValueError('Berita sudah diproses; tidak dapat dijadwalkan ulang.')
    if draft.status=='approved' and not planner_photo_only(db,draft):
        raise ValueError('Berita telah disiapkan untuk alur lain; tidak boleh dialihkan ke posting foto otomatis.')
    story=db.get(Story,draft.story_id)
    if not story or story.verification_status!='verified' or not evidence_ready(story):
        raise ValueError('Klaim sumber primer belum diverifikasi. Periksa Sumber & QC.')
    qc=report_for_draft(db,draft,story)
    if not qc.get('passed') or qc.get('style_review')!='passed':
        raise ValueError('QC editorial versi terbaru belum lulus. Klik Periksa QC dahulu.')
    if not photo_auto_safe(draft):
        raise ValueError('Cover HTTPS, kredit, lisensi, dan hak penggunaan foto belum terverifikasi.')
    # Both in-progress and successful posts occupy their original slot.
    occupied=db.execute(select(Draft).where(
        Draft.id!=draft.id,
        Draft.scheduled_at==utc,
        Draft.publish_state.in_(['unpublished','awaiting_container','publishing',
                                  'published','uncertain','manual_music_pending'])
    )).scalars().all()
    if occupied:
        raise ValueError('Slot tersebut sudah digunakan konten lain. Pilih tanggal/jam lain.')
    day=utc.astimezone(WIB).date()
    other=db.execute(select(Draft).where(
        Draft.id!=draft.id,Draft.scheduled_at.is_not(None),
        Draft.publish_state.in_(['unpublished','awaiting_container','publishing',
                                  'published','uncertain','manual_music_pending'])
    )).scalars().all()
    count=sum(1 for d in other if d.scheduled_at.astimezone(WIB).date()==day)
    if count>=CONFIG.daily_limit:
        raise ValueError('Batas tiga posting dalam satu hari sudah terisi.')
    if draft.expires_at and draft.expires_at<=utc:
        raise ValueError('Berita kedaluwarsa sebelum jadwal. Pilih berita baru.')
    if draft.status!='approved':
        approve(db,draft,actor)
    draft.rights_reviewed=True  # Verified by the stricter photo_auto_safe above.
    draft.scheduled_at=utc
    db.add(Audit(draft_id=draft.id,event='photo_only_approved',actor=actor,
                 detail={'version':draft.version,'source':'content_studio',
                         'note':'Owner chose automatic Instagram photo without music'}))
    db.add(Audit(draft_id=draft.id,event='content_plan_changed',actor=actor,
                 detail={'version':draft.version,'planned_at':utc.isoformat(),
                         'auto_publish':True,'channel':'instagram_photo_without_music'}))
    db.flush()
    return utc


def unschedule_web_post(db, draft, *, actor='web_content_studio'):
    if not pinned_planner_schedule(db,draft):
        raise ValueError('Hanya jadwal otomatis dari Content Studio yang dapat dibatalkan di sini.')
    # The earlier photo-only approval event is version-bound; remove approval
    # until the owner explicitly chooses another slot.
    draft.scheduled_at=None
    draft.status='pending_approval'
    draft.approved_version=None
    draft.approved_at=None
    draft.approved_by=None
    db.add(Audit(draft_id=draft.id,event='content_plan_changed',actor=actor,
                 detail={'version':draft.version,'planned_at':None,
                         'auto_publish':False}))
    db.flush()
