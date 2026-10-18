"""Regression coverage for container/runtime prerequisites and safe automation defaults."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]


def test_container_includes_live_editorial_guide():
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert "COPY docs/editorial-guide.md /app/docs/editorial-guide.md" in dockerfile
    assert "test -s /app/docs/editorial-guide.md" in dockerfile


def test_compose_uses_persistent_sqlite_for_local_demo():
    compose = (ROOT / "docker-compose.yml").read_text()
    assert compose.count("DATABASE_URL: ${DATABASE_URL:-sqlite:////app/state/ut_local.db}") == 2
    assert compose.count("- ut_state:/app/state") == 2
    assert "command: ['python', '-m', 'utbot.runner', 'loop']" in compose


def test_example_configuration_avoids_duplicate_settings():
    lines = (ROOT / ".env.example").read_text().splitlines()
    assignments = [line.split("=", 1)[0] for line in lines if line and not line.startswith("#") and "=" in line]
    assert len(assignments) == len(set(assignments))
    assert "AUTO_APPROVE_AFTER_24H=false" in lines
    assert "ENABLE_LIVE_PUBLISH=false" in lines
    assert "PHOTO_MUSIC_MODE=manual" in lines


def test_cron_entries_all_registered():
    data = json.loads((ROOT / "vercel.json").read_text())
    entries = data["crons"]
    assert len(entries) == 9
    assert len({row["path"] for row in entries}) == len(entries)
    assert all(row["schedule"].endswith("* * *") for row in entries)
