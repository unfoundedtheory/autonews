# Implementation status: v0.7

## Implemented and locally tested

- Fixed editorial four-line grid, original user-provided documentary photo, fixed badge; 1080×1350.
- Official RSS-source discovery, canonical URL fingerprint dedupe.
- Source-text extraction, literal evidence-quote validation and AI drafting.
- Multi-AI gateway (Gemini, DeepSeek, OpenAI, Anthropic, OpenRouter, Groq, Mistral, Together, Ollama).
- Licensed-image candidate search and source relevance gate, human license-review hold.
- Telegram approval, rejection, text rewriting, URL-based and direct photo upload, credit/license review.
- Local persistent worker loop, queue rollover, hourly discovery, 06/12/18 WIB slots, cap 2/day.
- Official Instagram API adapter with double-publish safeguards, dry-run disabled for live by default.
- Admin readiness, queue and status endpoints; GitHub test workflow, Docker Compose runtime.

## Not completed (requires external setup and real API testing)

- BotFather token, Telegram webhook and numeric owner IDs.
- Dedicated Supabase project, Postgres database, storage and service keys.
- Chosen AI API key(s), configured rate limits and safe budget.
- Meta Developer app, Instagram Professional account, proper scopes/token, first official test publish.
- New dedicated GitHub repository and remote push.
- Always-on public HTTPS container host.

Do not claim fully automatic publishing or successful integration until the items above are connected and the end-to-end tests are performed. The current "verified" story status only reflects literal source-quote matches from a trusted primary source; it is not cross-source independent verification.
