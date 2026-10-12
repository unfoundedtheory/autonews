"""Minimal safe local diagnostics; never echoes credential values."""
import sys
from utbot.config import CONFIG
from utbot.ai_provider import configured_providers
from utbot.renderer import BADGE_BOX, HEADLINE_TOP, HEADLINE_BOTTOM

def main():
    checks={
      'Telegram token': bool(CONFIG.telegram_token),
      'Telegram webhook secret':bool(CONFIG.telegram_secret),
      'Telegram admin allowlist':bool(CONFIG.admin_ids),
      'Telegram chat ID':bool(CONFIG.chat_id),
      'Worker secret':bool(CONFIG.worker_secret),
      'AI provider key':any(p!='ollama' for p in configured_providers()),
      'Instagram ID and token':bool(CONFIG.ig_user_id and CONFIG.ig_token),
      'Supabase image storage':bool(CONFIG.supabase_url and CONFIG.supabase_key),
      'Four-line design':True,
    }
    for name,ready in checks.items():
        print(f'{"OK" if ready else "MISSING" :7} {name}')
    print('Badge:',BADGE_BOX,'headline:',HEADLINE_TOP,'to',HEADLINE_BOTTOM)
    print('Live publishing:',CONFIG.live_publish)
    if not all(checks.values()) or not CONFIG.live_publish:
        print('NOT LIVE: setup and official API end-to-end tests still required.')

if __name__=='__main__':main()
