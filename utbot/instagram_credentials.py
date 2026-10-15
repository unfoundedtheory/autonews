"""Resolve only the approved Page's encrypted Instagram credentials for the worker."""
import os
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from .models import MetaConnection
from .config import CONFIG

def resolve_instagram_credentials(db):
    """Read existing OAuth connection; fail closed on ambiguity/corruption.

    Never return, print or log credentials in diagnostics. Legacy env fallback
    works only if there is no stored connection at all.
    """
    rows=db.execute(select(MetaConnection)).scalars().all()
    matching=[row for row in rows if row.page_name.strip().casefold()=='unfounded theory']
    if len(matching)>1:
        raise ValueError('Multiple Unfounded Theory Meta connections; cannot select')
    if matching:
        row=matching[0]
        key=os.getenv('META_TOKEN_ENCRYPTION_KEY','')
        if not key:
            raise ValueError('Meta encryption key not configured')
        try:
            token=Fernet(key.encode()).decrypt(row.encrypted_page_token.encode()).decode()
        except (InvalidToken,ValueError,TypeError):
            raise ValueError('Stored Meta credentials cannot be decrypted') from None
        if not row.instagram_id.isdigit() or not token:
            raise ValueError('Stored Instagram credentials are incomplete')
        return row.instagram_id,token
    if rows:
        raise ValueError('Unfounded Theory Page not connected')
    if CONFIG.ig_user_id and CONFIG.ig_token:
        return CONFIG.ig_user_id,CONFIG.ig_token
    raise ValueError('Instagram credentials not configured')
