"""Runtime settings. All credentials must be supplied as environment secrets."""
import os
from dotenv import load_dotenv
from dataclasses import dataclass
# Local .env is loaded only if present; production environment variables take precedence.
load_dotenv(override=False)

@dataclass(frozen=True)
class Config:
    database_url: str = os.getenv('DATABASE_URL', 'sqlite:///./ut_local.db')
    telegram_token: str = os.getenv('TELEGRAM_BOT_TOKEN', '')
    telegram_secret: str = os.getenv('TELEGRAM_WEBHOOK_SECRET', '')
    admin_ids: frozenset[int] = frozenset(int(s.strip()) for s in os.getenv('TELEGRAM_ADMIN_USER_IDS','').split(',') if s.strip().isdigit())
    chat_id: str = os.getenv('TELEGRAM_CHAT_ID','')
    worker_secret: str = os.getenv('WORKER_SECRET','')
    ig_base: str = os.getenv('INSTAGRAM_GRAPH_BASE','https://graph.facebook.com')
    ig_version: str = os.getenv('INSTAGRAM_GRAPH_VERSION','v24.0')
    ig_user_id: str = os.getenv('INSTAGRAM_USER_ID','')
    ig_token: str = os.getenv('INSTAGRAM_ACCESS_TOKEN','')
    # Native Instagram music for 4:5 photo posts is a deliberate manual step.
    # No silent fallback to photo-only publishing.
    photo_music_mode: str = os.getenv('PHOTO_MUSIC_MODE','manual')
    facebook_page_id: str = os.getenv('FACEBOOK_PAGE_ID','')
    facebook_page_token: str = os.getenv('FACEBOOK_PAGE_ACCESS_TOKEN','')
    facebook_graph_version: str = os.getenv('FACEBOOK_GRAPH_VERSION','v24.0')
    facebook_crosspost: bool = os.getenv('FACEBOOK_CROSSPOST','false').lower() == 'true'
    live_publish: bool = os.getenv('ENABLE_LIVE_PUBLISH','false').lower() == 'true'
    daily_limit: int = int(os.getenv('DAILY_PUBLISH_LIMIT','2'))
    # Editorial stock: up to three drafts per run, twice daily on Vercel.
    draft_stock_target: int = int(os.getenv('DRAFT_STOCK_TARGET','14'))
    prepare_batch_limit: int = int(os.getenv('PREPARE_BATCH_LIMIT','3'))
    # Only applies with real live IG credentials + approved editorial QC/photo rights.
    auto_approve_24h: bool = os.getenv('AUTO_APPROVE_AFTER_24H','true').lower() == 'true'
    ai_provider: str = os.getenv('AI_PROVIDER','gemini')
    model: str = os.getenv('GEMINI_MODEL','gemini-3.5-flash-lite')
    # Vercel permits temporary writes only under /tmp; final media is uploaded immediately.
    media_dir: str = '/tmp/unfounded-media' if os.getenv('VERCEL') else os.getenv('MEDIA_DIR', './media')  # nosec B108
    brand_logo: str = os.getenv('BRAND_LOGO_PATH','')
    font_path: str = os.getenv('BRAND_FONT_PATH','')
    supabase_url: str = os.getenv('SUPABASE_URL','')
    supabase_key: str = os.getenv('SUPABASE_SERVICE_ROLE_KEY','')
    media_bucket: str = os.getenv('SUPABASE_MEDIA_BUCKET','unfounded-media')

CONFIG=Config()
