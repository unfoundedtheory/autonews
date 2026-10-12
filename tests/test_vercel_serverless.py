import json
from pathlib import Path
from unittest.mock import Mock
import pytest
from fastapi import HTTPException
from sqlalchemy.engine import make_url
from utbot.web import cron_auth
from utbot.models import make_engine

def test_cron_schedules_wib():
    crons=json.loads((Path(__file__).parents[1]/'vercel.json').read_text())['crons']
    assert [(c['path'],c['schedule']) for c in crons] == [
      ('/api/cron/research','0 18 * * *'),
      ('/api/cron/tick/morning','0 23 * * *'),
      ('/api/cron/tick/noon','0 5 * * *'),
      ('/api/cron/tick/evening','0 11 * * *')]

def test_cron_secret_validation(monkeypatch):
    monkeypatch.setenv('CRON_SECRET','secret-local-test')
    with pytest.raises(HTTPException) as e:
        cron_auth(Mock(headers={'authorization':'Bearer wrong'}))
    assert e.value.status_code==403

def test_serverless_cron_refuses_sqlite(monkeypatch):
    monkeypatch.setenv('CRON_SECRET','secret-local-test')
    with pytest.raises(HTTPException) as e:
        cron_auth(Mock(headers={'authorization':'Bearer secret-local-test'}))
    assert e.value.status_code==503

def test_postgres_url_driver(monkeypatch):
    import utbot.models as models
    seen=[]
    monkeypatch.setattr(models,'create_engine',lambda url,**kw:seen.append(url) or 'fake-engine')
    assert make_engine('postgres://u:p@localhost:5432/testdb')=='fake-engine'
    assert make_url(seen[0]).drivername=='postgresql+psycopg'

def test_vercel_imports_fastapi():
    from api.index import app
    assert app.title=='Unfounded Theory Automation'
