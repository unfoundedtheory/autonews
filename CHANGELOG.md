# Change Log

## v0.6 — 10 October 2026 (staging)

- Corrected layout after measuring all SIX owner-supplied originals: badge bounding area stays `(402,900)-(678,948)`; headline begins at fixed y=981 and fits before y=1307.
- Tight character tracking (-2.5%) **without** merging words; minimum visual word spacing 0.20em / 12px. Four vs five headline lines adapt font and pitch within one fixed editorial box.
- Extracted user reference badge artwork and bundled as default package data (not an official high-resolution brand export).
- Demo uses pixels of original owner-provided astronomy photo for staging only, never a generated surrogate.
- Added fixed-grid regression tests for badge identity, headline positions and spacing, and unchanged top photo.
- AI 9-provider backend and all approval/publish safeguards unchanged.
- Local tests pass; no live API/Instagram/Telegram end-to-end claims.

## v0.5 — 10 October 2026 (staging)

- Renderer: B-style hook, full A text width (968px on a 1080px canvas), generous word gaps, 54–92px type auto-fit, image-native photo only and black progressive gradient. Original photo is not altered with generated artwork.
- Added nine adapter names: Gemini, DeepSeek, OpenAI, Anthropic/Claude, OpenRouter, Groq, Mistral, Together, and Ollama local.
- New per-task selectors: `AI_DRAFT_PROVIDER`, `AI_REWRITE_PROVIDER` with separate model overrides. Explicit opt-in for automatic failover and for paid failover.
- Failover only on 429/502/503/504; not on timeouts, invalid JSON or uncertain outcomes.
- Added private `/internal/ai/providers` configuration endpoint; never returns tokens or calls paid services.
- Added `python -m scripts.check_ai_config` for offline AI setup inspection.
- Added mocks for nine provider protocols and fallback policy. 44 tests passed offline.
- Kept Instagram LIVE publishing off by default, and approval via Telegram mandatory.

### Not tested yet

All nine providers require their own valid API keys/models and real staging connectivity testing. Instagram live posting, Telegram end-to-end, and production deployment are **not** claimed as done. Owner-supplied reference photo is design guidance only; licensing has not been independently checked.
