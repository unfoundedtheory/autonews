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


## Single-click approval QC recovery (2026-10-14)

Telegram **Approve** first verifies the draft status/version, source/facts and final
cover, then runs independent Gemini editorial QC **on the same click** only when
the current automated QC is missing, outdated or incomplete. Current passed QC
is cached to stay within free-tier API limits. Failed QC remains failed and
is saved before the approval attempt returns; no scheduled posting is created.
The Telegram message describes the concrete content issue or temporary AI
unavailability instead of exposing \`independent_style_qc_not_recorded\`.
A repeat click for the same draft version does not repeat a failed Gemini call.
The **Hasil QC** button is still available for an explicit retry after resolving
a temporary issue. Any headline/caption revision increments the draft version
and invalidates prior QC/approval, so the next approval requires fresh QC.

Pure manual imports with no automated provenance retain the existing human
editorial review path, but must still pass trusted-source fact checks, format
lint and final cover readiness. One click never bypasses a real failed
independent style review and never auto-publishes to Instagram.

## Instagram Drafts + safe unattended fallback + draft stock (October 2026)

- **Human approval (music remains mandatory):** immediately after approval, Telegram sends the final 4:5 cover as a photo, a copyable caption, and Instagram Drafts instructions. The editor opens Instagram, chooses **Add music**, saves the item in **Drafts**, and waits for the scheduled reminder. At the scheduled time Telegram only reminds the editor; Instagram is never told to publish an approved native-music draft. Confirm the real /p/ link in Telegram after publishing. Previously approved posts receive a once-only kit through the hourly maintenance job.
- **24-hour no-response fallback:** enabled by `AUTO_APPROVE_AFTER_24H=true`. An unapproved Pending Approval draft is only eligible 24 hours after its latest edit, and only with current passing independent AI QC, verified source/evidence, a public HTTPS cover, valid attribution/license, and acceptable photo rights. Previously approved music drafts are EXCLUDED. Auto-approved drafts get a version-bound `auto_approved_24h` audit event and are published via official Meta API **without music** at the next available posting slot. Automatic approval is DISABLED until `ENABLE_LIVE_PUBLISH=true`, an actual IG account ID/access token, and an installed official brand logo are present. Do not enable live until Meta permissions and a consented E2E test work.
- **Photo rights boundary:** a creator/rights confirmation recorded in `rights_reviewed` is accepted. The only non-manual exception is an attributable, explicitly public-domain/CC0 image originating from Wikimedia Commons' canonical file page and media host. CC BY, CC BY-SA, unidentified licensing, and generic official article hero images **do not** pass unattended fallback without prior rights review. Machine-readable metadata alone is not a universal legal guarantee; review source context before enabling unattended publication.
- **Stock instead of 3 drafts/day:** `DRAFT_STOCK_TARGET=14` pending/approved posts and `PREPARE_BATCH_LIMIT=3` per run (hard cap five) trigger top-ups at approximately **03:00 and 15:00 WIB**. That provides up to six new drafts per day when valid unused stories exist, without accumulating endless AI requests. The stock target does not change `DAILY_PUBLISH_LIMIT`, which remains **2** unless the owner explicitly changes it to 3. Approvals beyond available daily slots remain scheduled for subsequent days.
- **Timing:** Vercel Hobby cron execution can be late; hourly maintenance is not an exact 24-hour-to-the-minute guarantee. No API flow can save an editable Instagram Draft directly. The posting kit is a manual save-to-Drafts handoff.
- **Recovery:** the Telegram "Kirim Paket Instagram" button resends the kit on owner request; automatic maintenance sends only if no completed kit event exists. Never replay an ambiguous Instagram `media_publish` call automatically.
