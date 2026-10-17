"""Guard the minimum four automatic preparation runs per WIB day."""
import json
from pathlib import Path


def test_four_daily_news_preparation_crons():
    config=json.loads((Path(__file__).resolve().parents[1]/'vercel.json').read_text())
    crons={entry['path']:entry['schedule'] for entry in config['crons']}
    assert crons['/api/cron/prepare']=='0 20 * * *'  # 03:00 WIB
    assert crons['/api/cron/prepare/morning']=='0 2 * * *'  # 09:00 WIB
    assert crons['/api/cron/prepare/afternoon']=='0 8 * * *'  # 15:00 WIB
    assert crons['/api/cron/prepare/evening']=='0 14 * * *'  # 21:00 WIB
