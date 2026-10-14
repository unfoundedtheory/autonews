"""Version-bound QC preflight for Telegram's one-click Approve.

No silent editorial bypass: only a current passing independent review or the
existing trusted manual-import path may be approved. AI preflight is bounded to
one attempt per draft version, so repeated Telegram callbacks don't waste the
free AI quota. Results are committed before any potentially failing approval.
"""
from .models import Audit
from .editorial import evidence_ready, editorial_guide_sha256
from .quality_control import (
    QC_RUBRIC_VERSION, report_for_draft, run_draft_qc,
)

ISSUE_LABELS = {
    'insufficient_primary_quotes': 'Kutipan pendukung dari sumber primer belum cukup (minimal 2).',
    'independent_style_qc_unavailable': 'Pemeriksaan AI belum tersedia/berhasil; coba ulang lewat Hasil QC.',
    'cover_four_line_overflow': 'Judul tidak muat dalam desain cover empat baris.',
    'caption_paragraph_count': 'Caption harus terdiri dari 4–5 paragraf.',
    'ending_not_question': 'Caption perlu ditutup dengan pertanyaan yang relevan.',
    'qc_curiosity_gap': 'Hook belum menyisakan rasa penasaran yang jelas.',
    'qc_fact_integrity': 'Beberapa klaim atau angka belum cukup didukung sumber.',
    'qc_caption_story': 'Alur caption belum memenuhi panduan editorial.',
    'qc_reader_relevance': 'Kaitan berita terhadap pembaca belum cukup jelas.',
    'editorial_guide_updated': 'Panduan editorial berubah; QC harus diperbarui.',
    'curiosity_gap_rubric_missing': 'Rubrik QC perlu diperbarui.',
    'hook_press_release_style': 'Hook masih bergaya siaran pers.',
    'hook_press_release_summary': 'Hook terlalu berupa ringkasan administratif.',
    'hook_factual_summary_not_curiosity_gap': 'Hook menjelaskan isi berita terlalu lengkap.',
    'hook_clickbait': 'Hook terindikasi terlalu sensasional.',
    'highlight_length': 'Panjang headline belum sesuai ketentuan.',
    'hashtag_format': 'Jumlah/format hashtag belum sesuai ketentuan.',
}

# Don't show low-level "not recorded" when a more useful reason is available.
INTERNAL_ISSUES = {
    'independent_style_qc_not_recorded',
    'curiosity_gap_not_verified',
}

def latest_version_qc(db, draft):
    records = db.query(Audit).filter(
        Audit.draft_id == draft.id,
        Audit.event == 'editorial_qc',
    ).order_by(Audit.id.desc()).all()
    return next((r for r in records if (r.detail or {}).get('version') == draft.version), None), bool(records)


def preflight_approval(db, draft, story):
    """Ensure current independent QC when applicable. None is the legacy manual-import path.

    Call only after validating authenticated Telegram admin and draft version.
    Preflight never marks approval or changes the actual headline/caption.
    """
    if draft.status != 'pending_approval' or draft.publish_state != 'unpublished':
        return None
    if (not story or story.verification_status != 'verified' or not evidence_ready(story)
        or not (draft.image_url or draft.image_local_path)):
        return None  # approve() reports source/cover blockers without AI calls
    current, has_prior = latest_version_qc(db, draft)
    manual_hook = db.query(Audit.id).filter(
        Audit.draft_id == draft.id,
        Audit.event == 'manual_hook_submitted',
    ).first() is not None
    automated_origin = db.query(Audit.id).filter(
        Audit.draft_id == draft.id,
        Audit.event == 'primary_quotes_checked',
    ).first() is not None
    if not has_prior and not manual_hook and not automated_origin:
        # Existing manual imports had no AI review; maintain their explicit
        # human editorial approval, but still enforce factual evidence + lint.
        return None
    if current and (current.detail or {}).get('style_review') == 'skipped_for_mock_writer' and not manual_hook:
        return None
    report = report_for_draft(db, draft, story)
    if report['passed']:
        return report  # reuse valid QC to avoid AI quota usage
    if current:
        detail = current.detail or {}
        current_guide = detail.get('guide_sha256') == editorial_guide_sha256()
        current_rubric = detail.get('rubric_version') == QC_RUBRIC_VERSION
        if detail.get('trigger') == 'telegram_approve' and current_guide and current_rubric:
            return report  # no repeat charge/AI call for same version
        checks = detail.get('checks') or {}
        # A genuine current semantic rejection is not a missing-QC error.
        if (current_guide and current_rubric and
                detail.get('style_review') == 'rejected' and
                bool(checks) and any(v.get('passed') is False for v in checks.values())):
            return report

    # Missing/stale QC is repaired on the same click. No automatic publication
    # and no forced "passed=True" merely because editor clicked Approve.
    fresh = run_draft_qc(db, draft, story, trigger='telegram_approve')
    db.commit()  # keep failures visible even if scheduling/approval later fails
    return report_for_draft(db, draft, story)


def approval_qc_message(report):
    """Telegram-friendly, actionable QC diagnostics without raw internal codes."""
    codes = list(dict.fromkeys(report.get('issues') or []))
    actionable = [s for s in codes if s not in INTERNAL_ISSUES]
    details = [ISSUE_LABELS.get(s, s.replace('_', ' ').capitalize()) for s in actionable[:3]]
    checks = report.get('checks') or {}
    for name in ('curiosity_gap', 'fact_integrity', 'reader_relevance', 'caption_story'):
        row = checks.get(name) or {}
        if row.get('passed') is False and row.get('reason'):
            details.append(str(row['reason'])[:185])
            break
    note = str(report.get('note') or '').strip()
    if not details and note:
        details.append(note[:185])
    if not details:
        details.append('QC otomatis belum lengkap, silakan lihat detailnya.')
    return ('⚠️ Berita belum dijadwalkan karena QC belum lolos.\n\n' +
            '\n'.join('• ' + reason for reason in details[:4]) +
            '\n\nLihat 📋 Hasil QC untuk detail atau revisi bagian yang disebutkan. '
            'Setelah diperbaiki, tekan Approve kembali.')
