"""Owner-approved existing cover badge must be packaged for live publishing."""
from pathlib import Path
from dataclasses import replace
from utbot.config import CONFIG
from utbot.renderer import DEFAULT_BADGE


def test_approved_badge_is_real_and_default():
    badge=Path(CONFIG.brand_logo)
    assert badge == DEFAULT_BADGE
    assert badge.is_file() and badge.stat().st_size > 0


def test_explicit_logo_override_remains_possible(monkeypatch):
    from utbot.config import Config
    monkeypatch.setenv('BRAND_LOGO_PATH','/tmp/official-alternate.png')
    assert Config().brand_logo == '/tmp/official-alternate.png'
