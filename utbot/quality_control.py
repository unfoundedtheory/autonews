"""Editorial QC gate. Conservative automated checks, not a substitute for fact checking."""
import re
from .editorial import lint, evidence_ready

FILLERS=('di sinilah ceritanya jadi penting','menariknya lagi,','tentu saja,','tak bisa dimungkiri')
SENSATIONAL=('anda tidak akan percaya','fakta mengejutkan','dijamin viral','bikin geger')

def assess(highlight, caption, hashtags, evidence, *, tragedy=False, image=None, audio=None):
    issues=list(lint(highlight,caption,hashtags,tragedy=tragedy))
    h=highlight.casefold()
    c=caption.casefold()
    if any(s in h for s in SENSATIONAL): issues.append('hook_clickbait')
    if len(highlight) > 140: issues.append('hook_too_long')
    if re.match(r'(?i)^(?:misi|wahana|satelit)\b',highlight.strip()):
        issues.append('hook_factual_summary_not_curiosity_gap')
    if re.search(r'(?i)\b(?:bertujuan untuk|dirancang untuk|akan mempelajari|akan meneliti|untuk memahami|berhasil diluncurkan)\b',highlight):
        issues.append('hook_press_release_summary')
    if re.match(r'(?i)^(?:misi\s+)?(?:nasa|esa|peneliti|ilmuwan|badan|lembaga|tim\s+peneliti)\b',highlight.strip()):
        issues.append('hook_press_release_style')
    if re.search(r'(?i)\b(?:merilis|mengumumkan|akan melakukan|dijadwalkan|menggelar)\b',highlight):
        issues.append('hook_administrative_framing')
    if any(s in c for s in FILLERS): issues.append('caption_filler')
    if re.search(r'(?i)\b(?:breaking|hari ini|malam ini)\b',highlight) and not evidence:
        issues.append('urgent_hook_missing_evidence')
    if not isinstance(evidence,list) or len(evidence)<2:
        issues.append('insufficient_primary_quotes')
    if image is not None:
        if not image.get('license'):issues.append('image_license_missing')
        if not image.get('page_url'):issues.append('image_source_missing')
    if audio is not None and audio.get('selected') and not audio.get('usage_rights_verified'):
        issues.append('audio_rights_unverified')
    return {'passed':not issues,'issues':sorted(set(issues)),
            'manual_checks':['fact_context','visual_accuracy','image_license','audio_availability_and_rights']}

def report_for_draft(db,draft,story):
    from .models import Audit
    reports=db.query(Audit).filter(Audit.draft_id==draft.id,Audit.event=='editorial_qc').order_by(Audit.id.desc()).all()
    for row in reports:
        if (row.detail or {}).get('version')==draft.version:
            return row.detail
    result=assess(draft.highlight,draft.caption,draft.hashtags,story.evidence if story else [],
                  tragedy=bool(draft.is_tragedy))
    result['version']=draft.version
    result['status']='passed_automated' if result['passed'] else 'needs_manual_review'
    return result
