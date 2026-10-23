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

def publish_facebook_once(db,draft,*,actor="worker",poster=None,config=None,facebook_first=False):
    config=config or CONFIG
    if not (config.live_publish and (facebook_first or config.facebook_crosspost)):
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
    attempts=db.query(Audit).filter(
        Audit.draft_id==draft.id,
        Audit.event.in_(['facebook_publish_started','facebook_published','facebook_uncertain','facebook_rejected'])
    ).order_by(Audit.id.desc()).all()
    if attempts:
        published=next((event for event in attempts if event.event=='facebook_published'),None)
        if published:
            return {'facebook':'published','facebook_post_id':(published.detail or {}).get('post_id'),'already_attempted':True}
        # A 4xx is a definitive rejection. Only a fresh explicit owner retry
        # may retry it; a timeout or unknown result remains non-retryable.
        if not (facebook_first and actor.startswith('owner_retry:') and
                attempts[0].event=='facebook_rejected' and
                not any(a.event=='facebook_uncertain' for a in attempts)):
            return {'facebook':'already_attempted', 'requires_reconciliation':True}
    # Publication already requires current-version approval. Do not block a
    # confirmed Instagram post solely because an older review flag was false.
    if draft.status not in (('approved','published') if facebook_first else ('published',)) or draft.approved_version!=draft.version:
        return {'facebook':'blocked','reason':'Confirmed Instagram post with current-version approval required'}
    if not draft.image_url or not draft.image_url.startswith('https://'):
        return {'facebook':'blocked','reason':'No publicly hosted JPEG'}

    # The POST may succeed even if the HTTP response is lost. Reserve first.
    db.add(Audit(draft_id=draft.id,event='facebook_publish_started',actor=str(actor),
                 detail={'version':draft.version,'page_id':page_id}))
    db.commit()
    try:
        adapter=poster or MetaGraph(page_token,config.facebook_graph_version)
        if getattr(draft,'post_format','single')=='carousel':
            from .carousel import require_slide_set,compose_api_caption
            images=[slide['image_url'] for slide in require_slide_set(draft)]
            result=adapter.publish_page_album(page_id,images,compose_api_caption(draft) if len(images)<=10 else caption_text(draft,allow_missing_credit=True))
        else:
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
        match=re.fullmatch(r'Meta Graph HTTP (\d{3}) \(details withheld\)',reason)
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
