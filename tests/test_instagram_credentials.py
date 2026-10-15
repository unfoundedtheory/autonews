from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import pytest
from utbot.models import Base,MetaConnection
from utbot.instagram_credentials import resolve_instagram_credentials

def test_worker_uses_encrypted_page_connection(monkeypatch):
    key=Fernet.generate_key()
    monkeypatch.setenv('META_TOKEN_ENCRYPTION_KEY',key.decode())
    eng=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(eng)
    with sessionmaker(bind=eng)() as db:
        db.add(MetaConnection(page_id='100',instagram_id='200',page_name='Unfounded Theory',
            encrypted_page_token=Fernet(key).encrypt(b'page-token').decode()))
        db.commit()
        assert resolve_instagram_credentials(db)==('200','page-token')
        row=db.get(MetaConnection,'100')
        row.encrypted_page_token='invalid'
        db.commit()
        with pytest.raises(ValueError,match='cannot be decrypted'):
            resolve_instagram_credentials(db)

def test_worker_refuses_other_page(monkeypatch):
    monkeypatch.setenv('META_TOKEN_ENCRYPTION_KEY',Fernet.generate_key().decode())
    eng=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(eng)
    with sessionmaker(bind=eng)() as db:
        db.add(MetaConnection(page_id='900',instagram_id='901',page_name='Unrelated Page',
            encrypted_page_token='placeholder'))
        db.commit()
        with pytest.raises(ValueError,match='not connected'):
            resolve_instagram_credentials(db)
