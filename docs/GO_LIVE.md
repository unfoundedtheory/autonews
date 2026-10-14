# Unfounded Theory — Deployment and go-live (v0.7)

## Required connections (never paste tokens in chat)

1. **Dedicated data project.** Create a new Supabase project named `unfounded-theory`, separate from ORDAL. Use its **database connection URL**, project URL and the service-role secret. Configure the `unfounded-media` bucket as **public read** for final JPEG only. Restrict upload with server-side service-role key, not a browser key.
2. **Telegram.** Open [@BotFather](https://t.me/BotFather), create a bot and copy its token to `TELEGRAM_BOT_TOKEN`. Add your numeric Telegram user ID to `TELEGRAM_ADMIN_USER_IDS` and private chat ID to `TELEGRAM_CHAT_ID`. Create long random `WORKER_SECRET` and `TELEGRAM_WEBHOOK_SECRET` (32+ characters each).
3. **AI.** Create Gemini API key in [Google AI Studio](https://aistudio.google.com/apikey). Fill `GEMINI_API_KEY`; keep `AI_PROVIDER=gemini`, paid failover OFF. Optional other providers are in `.env.example`.
4. **Instagram.** Switch to an eligible **Instagram Professional** account, configure Meta Developer app with approved publishing access, perform proper authorization and place the granted IG account ID/token into `INSTAGRAM_USER_ID` / `INSTAGRAM_ACCESS_TOKEN`. Review token expiry and permission scope. Never use Instagram password or browser automation.
5. **Server.** Have an always-on Docker-capable HTTPS host with persistent media storage and a reverse proxy (or a managed container host with a persistent volume). Vercel's ephemeral serverless filesystem is not appropriate for this existing FastAPI + long-running worker layout. The backend uses one worker process to avoid scheduling collisions.

## Start safely

```bash
cp .env.example .env
# Set database, Telegram, worker and AI secrets; ENABLE_LIVE_PUBLISH=false.
docker compose up --build -d
curl https://YOUR-HOST/health
curl -H "x-worker-secret: $WORKER_SECRET" https://YOUR-HOST/internal/readiness
```

Host the API behind HTTPS on port 443 and proxy to `api:8000`. Never expose port 8000 or the database publicly. For a local Docker demo only, the compose file maps to `127.0.0.1:8000` and preserves SQLite data and media in named volumes. The worker will discover every two hours (WIB), prepare drafts and publish due posts in five-minute windows; publication is blocked while `ENABLE_LIVE_PUBLISH=false`.

## Telegram webhook

Set the Telegram webhook URL to `https://YOUR-HOST/telegram/webhook` and `secret_token` to your `TELEGRAM_WEBHOOK_SECRET`. Use the Telegram API `setWebhook` from your own machine. Do **not** paste the complete command with a bot token into a shared log or chat.

Admin commands: `/help`, `/pending`, `/queue`, `/status`. In each draft: review image and source, optionally supplement photo credit/license, then explicitly Approve once. No separate rights-verification callback is needed in the manual photo+music mode. The editor remains responsible for lawful use; no missing license is deemed automatically verified. Approval becomes invalid on each revision.

## Mandatory pre-publish checks

- Render with a genuine, relevant source photo in **four lines**, badge at exact fixed grid coordinates.
- Confirm primary source quoted text and all five captions/hashtags rules. This automated quote check is not independent multi-source fact-checking.
- Confirm image usage rights. Credit and license are carried into the published caption.
- Approve through Telegram. Confirm the image is publicly downloadable via HTTPS from Instagram infrastructure, not only a local path.
- Trigger the publishing path with the approved test draft and correct official Meta permission/token. Confirm that an ambiguous publish timeout moves to `uncertain` and does **not** retry blindly.
- Test expiry, queue rollover (2/day), 06/12/18 WIB slots, server restart, Telegram old buttons, and paid AI fallback disabled.
- Only then update the deployment secret `ENABLE_LIVE_PUBLISH=true` and restart the affected services; verify publishing with one consented test post.

## Known limitations

- Credentials and a dedicated cloud project are not present in the source archive. No claim of production activation is made.
- Cross-source independent verification, semantic dedupe of repeated stories and Meta token rotation still require further development and live testing.
- Telegram bot uses synchronous outbound actions; on a slow image search webhook processing may exceed provider deadlines. Prefer a task queue if volume increases.
- Do not scale the worker beyond one replica without distributed locking and queue redesign.

## Native music photo-feed mode (new)

The owner selected Instagram **4:5 feed photo with native Instagram music**, NOT a Reel. The standard Graph API image container does not accept licensed catalog audio. Use `PHOTO_MUSIC_MODE=manual` and keep `ENABLE_LIVE_PUBLISH=false` while onboarding. Scheduled approved stories are sent as a Telegram posting kit; the operator uploads the original 4:5 photo and uses Instagram's Add Music flow, then confirms a valid `/p/<code>/` URL to the bot. This confirmation is explicitly user-attested and does not prove that the music was applied. Do not switch to silent photo API publication without a deliberate explicit change to `PHOTO_MUSIC_MODE=off`.

Facebook Page auto-post is a distinct optional API action; link an actual Page with permissions and test read-only `GET /api/internal/meta/connection` before setting `FACEBOOK_CROSSPOST=true`. Check whether Meta Business Suite/Instagram already shares to Facebook so there is exactly ONE posting method. There is NO automatic transfer of the native Instagram track to a Facebook Page photo through the Graph API. On ambiguous Facebook POST results, audit records `facebook_uncertain` and never retries.
