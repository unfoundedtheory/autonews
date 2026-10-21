"""Optional independent Facebook Page post after confirmed Instagram publication.

All attempts are durably recorded *before* posting. An uncertain Graph API
outcome must NEVER be reissued automatically. Native IG→FB sharing may already
be enabled; this option stays disabled until the owner explicitly opts in.
"""
from .models import Audit, MetaConnection
import httpx
import re
from sqlalchemy import select
from .config import CONFIG
from .meta import MetaGraph
from .instagram import caption_text

def publish_facebook_once(db,draft,*,actor="worker",poster=None,config=None):
    config=config or CONFIG
    if not (config.facebook_crosspost and config.live_publish):
        return {'facebook':'disabled'}
    # OAuth already stores a Page token encrypted at rest. Prefer the owner-
    # authorized Page rather than requiring a second independent token setup.
    page_id, page_token = config.facebook_page_id, config.facebook_page_token
    if not (page_id and page_token):
        rows=db.execute(select(MetaConnection)).scalars().all()
        matches=[row for row in rows if row.page_name.strip().casefold()=='unfounded theory']
        if len(matches)!=1:
            return {'facebook':'not_configured'}
        import os
        from cryptography.fernet import Fernet, InvalidToken
        key=os.getenv('META_TOKEN_ENCRYPTION_KEY','')
        if not key:
            return {'facebook':'not_configured'}
        try:
            page_token=Fernet(key.encode()).decrypt(matches[0].encrypted_page_token.encode()).decode()
        except (InvalidToken,ValueError,TypeError):
            return {'facebook':'not_configured'}
        page_id=matches[0].page_id
    if not page_id or not page_token:
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
        Audit.event.in_(['facebook_publish_started','facebook_published','facebook_uncertain','facebook_rejected'])
    ).first()
    if previous:
        return {'facebook':'already_attempted', 'requires_reconciliation':True}
    # Publication already requires current-version approval. Do not block a
    # confirmed Instagram post solely because an older review flag was false.
    if draft.status!='published' or draft.approved_version!=draft.version:
        return {'facebook':'blocked','reason':'Confirmed Instagram post with current-version approval required'}
    if not draft.image_url or not draft.image_url.startswith('https://'):
        return {'facebook':'blocked','reason':'No publicly hosted JPEG'}

    # The POST may succeed even if the HTTP response is lost. Reserve first.
    db.add(Audit(draft_id=draft.id,event='facebook_publish_started',actor=str(actor),
                 detail={'version':draft.version,'page_id':page_id}))
    db.commit()
    try:
        adapter=poster or MetaGraph(page_token,config.facebook_graph_version)
        result=adapter.publish_page_photo(page_id,draft.image_url,
                                          caption_text(draft,allow_missing_credit=True))
        db.add(Audit(draft_id=draft.id,event='facebook_published',actor=str(actor),
                     detail={'page_id':page_id,
                             'photo_id':result['photo_id'],'post_id':result['id']}))
        db.commit()
        return {'facebook':'published','facebook_post_id':result['id']}
    except Exception as exc:
        db.rollback()
        # Never persist access tokens, URLs, captions, or raw Graph responses.
        # A Graph 4xx is a definitive rejection; timeouts/5xx may have posted.
        reason=str(exc)
        match=re.fullmatch(r'Meta Graph HTTP (\\d{3}) \\(details withheld\\)',reason)
        status=int(match.group(1)) if match else None
        rejected=status is not None and 400 <= status < 500
        event='facebook_rejected' if rejected else 'facebook_uncertain'
        category=('graph_http_'+str(status) if status else
                  'network_timeout' if isinstance(exc,httpx.TimeoutException) else
                  'network_error' if isinstance(exc,httpx.TransportError) else
                  'unexpected_response_or_error')
        db.add(Audit(draft_id=draft.id,event=event,actor=str(actor),
                     detail={'category':category,'exception_type':type(exc).__name__,
                             'version':draft.version,
                             'note':'Verify Page permissions and OAuth token' if rejected
                             else 'Check Page before any new attempt'}))
        db.commit()
        return {'facebook':'rejected' if rejected else 'uncertain',
                'reason':category,'requires_reconciliation':not rejected}
