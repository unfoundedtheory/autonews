from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import create_engine, Column, String, Integer, DateTime, Boolean, ForeignKey, Text, JSON
from sqlalchemy.types import TypeDecorator
from sqlalchemy.orm import declarative_base, sessionmaker
from .config import CONFIG

Base=declarative_base()

class UTCDateTime(TypeDecorator):
    """Keep UTC awareness when SQLite drops timezone metadata in local tests."""
    impl=DateTime
    cache_ok=True

    def load_dialect_impl(self,dialect):
        return dialect.type_descriptor(DateTime(timezone=dialect.name!='sqlite'))

    def process_bind_param(self,value,dialect):
        if value is None:return None
        value=value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
        return value.replace(tzinfo=None) if dialect.name=='sqlite' else value

    def process_result_value(self,value,dialect):
        if value is None:return None
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

def utcnow():
    return datetime.now(timezone.utc)

class Story(Base):
    __tablename__="stories"
    id=Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    fingerprint=Column(String(64), nullable=False, unique=True)
    title=Column(Text, nullable=False)
    source_url=Column(Text, nullable=False)
    source_name=Column(String(120), nullable=False)
    published_at=Column(UTCDateTime(), nullable=True)
    topic=Column(String(40), nullable=False, default="astronomy")
    verification_status=Column(String(32), nullable=False, default="needs_fact_check")
    evidence=Column(JSON, nullable=False, default=list)
    created_at=Column(UTCDateTime(), nullable=False, default=utcnow)

class Draft(Base):
    __tablename__="drafts"
    id=Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    story_id=Column(String(36), ForeignKey("stories.id"), nullable=False, unique=True)
    version=Column(Integer, nullable=False, default=1)
    highlight=Column(Text, nullable=False)
    caption=Column(Text, nullable=False)
    hashtags=Column(JSON, nullable=False)
    # image_url is ALWAYS the fully rendered, publicly hosted 4:5 post; never an unprocessed photo.
    image_url=Column(Text, nullable=True)
    post_format=Column(String(12), nullable=False, default="single")
    carousel_slides=Column(JSON, nullable=False, default=list)
    source_image_url=Column(Text, nullable=True)
    source_image_path=Column(Text, nullable=True)
    media_page_url=Column(Text, nullable=True)
    image_license_url=Column(Text, nullable=True)
    photo_candidates=Column(JSON, nullable=False, default=list)
    accent_words=Column(JSON, nullable=False, default=list)
    is_tragedy=Column(Boolean, nullable=False, default=False)
    image_local_path=Column(Text, nullable=True)
    image_credit=Column(Text, nullable=True)
    photo_license=Column(String(120), nullable=True)
    rights_reviewed=Column(Boolean, nullable=False, default=False)
    status=Column(String(30), nullable=False, default="pending_approval")
    approved_version=Column(Integer, nullable=True)
    approved_by=Column(String(50), nullable=True)
    approved_at=Column(UTCDateTime(), nullable=True)
    scheduled_at=Column(UTCDateTime(), nullable=True)
    expires_at=Column(UTCDateTime(), nullable=True)
    ig_container_id=Column(String(80), nullable=True, unique=True)
    ig_media_id=Column(String(80), nullable=True, unique=True)
    publish_state=Column(String(30), nullable=False, default="unpublished")
    last_error=Column(Text, nullable=True)
    created_at=Column(UTCDateTime(), nullable=False, default=utcnow)
    updated_at=Column(UTCDateTime(), nullable=False, default=utcnow, onupdate=utcnow)

class Audit(Base):
    __tablename__="audit"
    id=Column(Integer, primary_key=True, autoincrement=True)
    draft_id=Column(String(36), nullable=False)
    event=Column(String(80), nullable=False)
    actor=Column(String(80), nullable=False)
    detail=Column(JSON, default=dict)
    created_at=Column(UTCDateTime(), nullable=False, default=utcnow)

class MetaConnection(Base):
    """Owner-authorized Instagram linkage; Page token stored encrypted at rest."""
    __tablename__="meta_connections"
    page_id=Column(String(80),primary_key=True)
    instagram_id=Column(String(80),nullable=False)
    page_name=Column(String(200),nullable=False)
    encrypted_page_token=Column(Text,nullable=False)
    updated_at=Column(UTCDateTime(),nullable=False,default=utcnow)


class MetaPageChoice(Base):
    """Short-lived encrypted candidates; no Meta tokens in pages or cookies."""
    __tablename__="meta_page_choices"
    id=Column(String(64),primary_key=True)
    encrypted_candidates=Column(Text,nullable=False)
    expires_at=Column(UTCDateTime(),nullable=False)
    created_at=Column(UTCDateTime(),nullable=False,default=utcnow)


class TelegramUpdateReceipt(Base):
    """Durable Telegram webhook de-duplication across serverless retries."""
    __tablename__="telegram_update_receipts"
    update_id=Column(String(40), primary_key=True)
    received_at=Column(UTCDateTime(), nullable=False, default=utcnow)


class TelegramSession(Base):
    __tablename__="telegram_sessions"
    user_id=Column(String(50), primary_key=True)
    draft_id=Column(String(36), nullable=False)
    mode=Column(String(20), nullable=False)
    version=Column(Integer, nullable=False)
    updated_at=Column(UTCDateTime(), nullable=False, default=utcnow)


def make_engine(url=None):
    url=url or CONFIG.database_url
    if url.startswith('postgres://'):
        url='postgresql+psycopg://' + url[len('postgres://'):]
    elif url.startswith('postgresql://'):
        url='postgresql+psycopg://' + url[len('postgresql://'):]
    return create_engine(url, connect_args={"check_same_thread":False} if url.startswith("sqlite") else {}, pool_pre_ping=True)

engine=make_engine()
Session=sessionmaker(bind=engine, expire_on_commit=False)

def init_db(engine_=None):
    Base.metadata.create_all(engine_ or engine)
