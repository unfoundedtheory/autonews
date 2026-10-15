# Connect Instagram (owner-only)

Production project: `unfoundedtheory/autonews` (Vercel `autonews`).
Canonical hostname: `https://unfoundedtheory.vercel.app`.

## Meta Developer

In Facebook Login for Business > Settings > Valid OAuth Redirect URIs,
add exactly:

`https://unfoundedtheory.vercel.app/api/meta/callback`

Keep Web OAuth Login, Strict Mode and HTTPS enabled.
Use existing "AutoNews Instagram Connection" configuration ID
`1845302206633686` (not an App ID).

## Production environment (Vercel)

Set **secrets only in Vercel**, never GitHub or Telegram:

- `META_APP_ID`: Meta App ID from App Settings > Basic; **not the Instagram app ID**.
- `META_APP_SECRET`: from App Settings > Basic.
- `META_LOGIN_CONFIG_ID`: `1845302206633686`
- `META_CONNECT_PASSWORD`: a strong dedicated admin password.
- `META_TOKEN_ENCRYPTION_KEY`: a Fernet key generated with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
- `META_OAUTH_BASE_URL`: `https://unfoundedtheory.vercel.app`

Install `cryptography` and `python-multipart` from pyproject.toml. The database
must be persistent PostgreSQL. The `meta_connections` table is created by
the app's existing startup schema initialization; production migration review
is required before applying.

## Owner workflow

Open `https://unfoundedtheory.vercel.app/api/meta/connect`, enter admin
password, authorize Meta Page/Instagram, and land on a read-only result page.
Tokens are encrypted server-side. This does not enable automatic posting;
production photo-only fallback requires an additional token lifecycle and live
end-to-end verification before enabling `ENABLE_LIVE_PUBLISH`.

If the login is unavailable, verify that your Facebook personal profile is
assigned an app role and has access to the desired Page and linked
Instagram Professional account. Restrict the app to owner testing until complete.

## Security

Never paste access tokens or secrets into chat/screenshots.
OAuth state is signed, short-lived, cookie-bound, HTTPS-only.
Tokens are not returned by callback, status, or logs.
