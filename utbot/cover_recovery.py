"""Recover a preview cover from its exact primary article, never auto-clear media rights."""
from pathlib import Path
from .config import CONFIG
from .media import find_article_photo,intake_image,render_draft
from .photo_sources import discover_cover_candidates
from .editorial import revise
from .renderer import require_cover_fit


def recover_article_cover(db,draft,story,actor='editor',*,finder=None,intake=None,renderer=None):
    """Only pending drafts. Render uploads on Vercel; source image remains unlicensed."""
    if draft.status!='pending_approval' or draft.publish_state in {'publishing','published','uncertain','awaiting_container'}:
        raise ValueError('Hanya draf pending yang dapat diperbaiki.')
    require_cover_fit(draft.highlight,CONFIG.font_path)
    # Explicit test/preview providers keep their old one-argument interface.
    # Automatic recovery must check subject relevance before rendering.
    if finder is not None:
        candidate=finder(story.source_url)
        candidates=[candidate] if candidate else []
    else:
        candidates,_errors=discover_cover_candidates(story)
    if not candidates:
        raise ValueError('Tidak ditemukan foto yang relevan dari sumber alternatif.')
    source_path=Path(CONFIG.media_dir)/draft.id/f'source_v{draft.version+1}.jpg'
    photo_url=None
    candidate=None
    for item in candidates:
        for link in dict.fromkeys(
                url for url in (item.get('image_url'),item.get('original_url')) if url):
            try:
                (intake or intake_image)(link,str(source_path))
                photo_url=link
                candidate=item
                break
            except (ValueError,RuntimeError,OSError,__import__('httpx').HTTPError):
                continue
        if photo_url:
            break
    if not photo_url:
        raise ValueError('Foto alternatif tersedia tetapi unduhan tidak berhasil.')
    revise(db,draft,'source_image_url',photo_url,actor)
    draft.source_image_path=str(source_path)
    draft.media_page_url=candidate.get('page_url') or story.source_url
    draft.image_credit=candidate.get('credit')
    draft.photo_license=candidate.get('license')
    draft.image_license_url=candidate.get('license_url')
    draft.rights_reviewed=False
    draft.photo_candidates=[]
    (renderer or render_draft)(draft)
    draft.last_error=None
    return draft
