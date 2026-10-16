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
    import subprocess
    import sys
    monkeypatch.setenv('BRAND_LOGO_PATH','/tmp/official-alternate.png')
    result=subprocess.check_output([sys.executable,'-c',
        'from utbot.config import CONFIG; print(CONFIG.brand_logo)'], text=True)
    assert result.strip() == '/tmp/official-alternate.png'
