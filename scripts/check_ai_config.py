"""Offline provider configuration check; never prints keys or sends paid requests."""
import os
from utbot.ai_provider import PROVIDERS


def main():
    active = os.getenv('AI_PROVIDER', 'gemini').lower()
    draft = os.getenv('AI_DRAFT_PROVIDER') or active
    rewrite = os.getenv('AI_REWRITE_PROVIDER') or active
    print('Primary:', active)
    print('Draft:', draft)
    print('Rewrite:', rewrite)
    print('Automatic fallback:', os.getenv('AI_ENABLE_FALLBACK', 'false').lower() == 'true')
    print('Paid fallback:', os.getenv('AI_ALLOW_PAID_FALLBACK', 'false').lower() == 'true')
    print('Available adapters (credentials checked; no API requests):')
    for name, cfg in PROVIDERS.items():
        present = bool(os.getenv(cfg.key_env, '')) if cfg.key_env else False
        print(f'  {name:12s} {"key set" if present else "local / key not set" if not cfg.key_env else "key missing"}')
    for role, name in [('default', active), ('draft', draft), ('rewrite', rewrite)]:
        if name not in PROVIDERS:
            raise SystemExit(f'Invalid {role} provider: {name}')
    print('No external connection tests performed.')


if __name__ == '__main__':
    main()
