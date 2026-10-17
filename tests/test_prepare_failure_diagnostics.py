"""Failed preparation is never described as a running background AI job."""
from unittest.mock import patch
from utbot.web import generate_news_now


def test_generation_failure_reports_real_state_and_reason():
    class DummyDB:
        def commit(self): pass
    failed=[{'status':'retry_pending','reason':'HTTPStatusError','http_status':429}]
    with patch('utbot.web.prepare_batch',return_value=failed), \
         patch('utbot.research.discover',return_value=[]):
        msg=generate_news_now(DummyDB(),None,42)
    assert 'GAGAL' in msg
    assert 'HTTP 429' in msg
    assert 'Belum ada AI yang bekerja di latar belakang' in msg
    assert 'sedang memperbaiki' not in msg


def test_generation_failure_explains_invalid_draft():
    class DummyDB:
        def commit(self): pass
    failed=[{'status':'retry_pending','reason':'ValueError','http_status':None}]
    with patch('utbot.pipeline.prepare_batch',return_value=failed), \
         patch('utbot.research.discover',return_value=[]):
        msg=generate_news_now(DummyDB(),None,42)
    assert 'ValueError' in msg
    assert 'GAGAL' in msg
