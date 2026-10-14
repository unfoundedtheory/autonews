"""Recover a preview cover from its exact primary article, never auto-clear media rights."""
from pathlib import Path
from .config import CONFIG
from .media import find_article_photo,intake_image,render_draft
from .editorial import revise
from .renderer import require_cover_fit


def recover_article_cover(db,draft,story,actor='editor',*,finder=None,intake=None,renderer=None):
    """Only pending drafts. Render uploads on Vercel; source image remains unlicensed."""
    if draft.status!='pending_approval' or draft.publish_state in {'publishing','published','uncertain','awaiting_container'}:
        raise ValueError('Hanya draf pending yang dapat diperbaiki.')
    require_cover_fit(draft.highlight,CONFIG.font_path)
    candidate=(finder or find_article_photo)(story.source_url)
    if not candidate or not candidate.get('image_url'):
        raise ValueError('Artikel sumber tidak menyediakan foto utama yang layak.')
    photo_url=candidate['image_url']
    source_path=Path(CONFIG.media_dir)/draft.id/f'source_v{draft.version+1}.jpg'
    (intake or intake_image)(photo_url,str(source_path))
    revise(db,draft,'source_image_url',photo_url,actor)
    draft.source_image_path=str(source_path)
    draft.media_page_url=candidate.get('page_url') or story.source_url
    draft.image_credit=None
    draft.photo_license=None
    draft.image_license_url=None
    draft.rights_reviewed=False
    draft.photo_candidates=[]
    (renderer or render_draft)(draft)
    draft.last_error=None
    return draft
