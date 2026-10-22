"""Prevent deleted/previously published photos from silently returning."""
from urllib.parse import urlsplit,urlunsplit
from sqlalchemy import select
from .models import Draft,Story

def image_identity(url):
    if not url:return ""
    p=urlsplit(url.strip())
    return urlunsplit((p.scheme.lower(),p.netloc.lower(),p.path,"",""))

def reused_photo(db,draft):
    key=image_identity(draft.source_image_url)
    if not key:return None
    rows=db.execute(select(Draft).where(Draft.id!=draft.id,
         Draft.source_image_url.is_not(None),
         Draft.status.in_(["approved","published","removed_by_owner"]),
    )).scalars().all()
    for old in rows:
        if image_identity(old.source_image_url)==key:
            return old
    return None

def auto_visual_safe(db,draft,story):
    """A reused generic NASA picture is not evidence for an unrelated article."""
    if reused_photo(db,draft):
        return False,"previously_used_photo"
    from .photo_relevance import photo_subject_match
    item={"title":getattr(draft,"image_credit",None) or "",
          "description":getattr(draft,"media_page_url",None) or ""}
    if not photo_subject_match(story.title,item,story.title):
        return False,"photo_subject_unverified"
    return True,"ok"
