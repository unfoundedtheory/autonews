"""Optional independent Facebook Page post after confirmed Instagram publication.

All attempts are durably recorded *before* posting. An uncertain Graph API
outcome must NEVER be reissued automatically. Native IG→FB sharing may already
be enabled; this option stays disabled until the owner explicitly opts in.
"""
from .models import Audit
from .config import CONFIG
from .meta import MetaGraph
from .instagram import caption_text

def publish_facebook_once(db,draft,*,actor="worker",poster=None,config=None):
    config=config or CONFIG
    if not (config.facebook_crosspost and config.live_publish):
        return {'facebook':'disabled'}
    if not config.facebook_page_id or not config.facebook_page_token:
        return {'facebook':'not_configured'}
    # Serialize concurrent Page posts for the same draft in PostgreSQL. Once
    # facebook_publish_started is committed, no worker may retry blindly.
    if db.bind.dialect.name=='postgresql':
        from sqlalchemy import text
        import hashlib
        key=int.from_bytes(hashlib.sha256(draft.id.encode()).digest()[:8],'big',signed=True)
        db.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':key})
    previous=db.query(Audit).filter(
        Audit.draft_id==draft.id,
        Audit.event.in_(['facebook_publish_started','facebook_published','facebook_uncertain'])
    ).first()
    if previous:
        return {'facebook':'already_attempted', 'requires_reconciliation':True}
    if draft.status!='published' or not draft.rights_reviewed:
        return {'facebook':'blocked','reason':'Instagram confirmation and photo rights required'}
    if not draft.image_url or not draft.image_url.startswith('https://'):
        return {'facebook':'blocked','reason':'No publicly hosted JPEG'}

    # The POST may succeed even if the HTTP response is lost. Reserve first.
    db.add(Audit(draft_id=draft.id,event='facebook_publish_started',actor=str(actor),
                 detail={'version':draft.version,'page_id':config.facebook_page_id}))
    db.commit()
    try:
        adapter=poster or MetaGraph(config.facebook_page_token,config.facebook_graph_version)
        result=adapter.publish_page_photo(config.facebook_page_id,draft.image_url,
                                          caption_text(draft,allow_missing_credit=True))
        db.add(Audit(draft_id=draft.id,event='facebook_published',actor=str(actor),
                     detail={'page_id':config.facebook_page_id,
                             'photo_id':result['photo_id'],'post_id':result['id']}))
        db.commit()
        return {'facebook':'published','facebook_post_id':result['id']}
    except Exception:
        db.rollback()
        db.add(Audit(draft_id=draft.id,event='facebook_uncertain',actor=str(actor),
                     detail={'note':'Check Page before any new attempt'}))
        db.commit()
        return {'facebook':'uncertain','requires_reconciliation':True}
