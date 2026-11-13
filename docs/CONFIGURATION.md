# Configuration Reference

Ethiogen has two configuration layers:

1. **Environment / `settings.py`** — bootstrap values, database, Django security, and defaults.
2. **Integration settings row** — editable at `/admin/settings/` and stored in the database.

For integration values, the database row wins. This lets an administrator rotate a Telegram token or change the Chapa key without editing `.env` or restarting the bot.

## 1. Resolution order

`billing/config.py` resolves each value in this order:

```
1. IntegrationSettings row (pk=1)
2. settings.py value / environment variable
3. built-in default
```

The row is cached for **30 seconds**. Saving the settings page calls `invalidate_cache()`, so the web process sees the change immediately. The bot process refreshes within the TTL.

## 2. Environment template

The canonical list is [`.env.example`](../.env.example). The important groups are below.

### Django

| Variable | Default | Purpose |
|---|---|---|
| `DJANGO_DEBUG` | off | Set `1`/`true`/`yes`/`on` for local development |
| `DJANGO_SECRET_KEY` | insecure fallback | **Set a long random value in production** |
| `DJANGO_ALLOWED_HOSTS` | `*` | Comma-separated hostnames |
| `CORS_ALLOWED_ORIGINS` | empty | Comma-separated origins for the mini app; empty denies all |
| `CSRF_TRUSTED_ORIGINS` | empty | Must include cross-origin POST origins (scheme + host) |

### Database

| Variable | Default | Purpose |
|---|---|---|
| `DB_ENGINE` | `sqlite` | `postgresql`/`postgres`/`psql` switches to PostgreSQL |
| `DB_NAME` | `ethiogen` | PostgreSQL database |
| `DB_USER` | `postgres` | PostgreSQL user |
| `DB_PASSWORD` | empty | PostgreSQL password |
| `DB_HOST` | `127.0.0.1` | PostgreSQL host |
| `DB_PORT` | `5432` | PostgreSQL port |
| `DB_CONN_MAX_AGE` | `60` | Persistent connection age |
| `DB_SSLMODE` | unset | e.g. `require` for managed PostgreSQL |

SQLite uses `db.sqlite3` with a 20-second lock timeout.

### Telegram

| Variable | Read by | Purpose |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | settings + bot | Bot token from @BotFather |
| `ETHIOGEN_BOT_TOKEN` | settings fallback | Alternate name accepted for the same token |
| `ETHIOGEN_UPDATE_GROUP_ID` | `settings.TELEGRAM_CHANNEL_ID` + bot | Channel/group ID used for publishing and scraping |
| `TELEGRAM_CHANNEL_ID` | *not read directly* | Kept in the template for compatibility; use `ETHIOGEN_UPDATE_GROUP_ID` or the admin settings row |
| `TELEGRAM_CHANNEL_USERNAME` | *not read directly* | Kept in the template for compatibility; use `ETHIOGEN_CHANNEL_USERNAME` or the admin settings row |
| `ETHIOGEN_CHANNEL_USERNAME` | `settings.TELEGRAM_CHANNEL_USERNAME` + bot | Channel username (without `@`) |
| `ETHIOGEN_BOT_USERNAME` | bot/start script | Bot username |
| `ETHIOGEN_ADMIN_IDS` | `config.telegram_admin_ids()` fallback | Comma-separated Telegram user IDs allowed to use admin commands |
| `TELEGRAM_GROUP_ID` | `config.telegram_group_id()` | Optional discussion group |
| `TELEGRAM_CHAT_ID` | settings only | Legacy/default chat id, defaults to `@your_channel_username`; not used by the billing config accessors |
| `WHISPER_MODEL` | transcription | Whisper model size (`base` by default) |

> **Channel ID nuance:** `settings.TELEGRAM_CHANNEL_ID` is populated from `ETHIOGEN_UPDATE_GROUP_ID`, not from `TELEGRAM_CHANNEL_ID`. If publishing goes to the wrong place, set `ETHIOGEN_UPDATE_GROUP_ID` or set the channel ID in the admin settings row.

Admin settings row fields (take precedence):

- `telegram_bot_token`
- `telegram_bot_username`
- `telegram_channel_id`
- `telegram_channel_username`
- `telegram_group_id`
- `telegram_admin_ids`
- `telegram_website_url`

### Billing and payments

| Variable | Default | Purpose |
|---|---|---|
| `BILLING_CURRENCY` | `ETB` | Display currency |
| `BILLING_SUBSCRIPTION_PRICE` | `500.00` | Default price |
| `BILLING_SUBSCRIPTION_DAYS` | `30` | Default duration |
| `BILLING_SITE_URL` | `https://ethiogen.com` | Used in links and Chapa return URLs |
| `BILLING_BANK_NAME` | Commercial Bank of Ethiopia | Manual bank details |
| `BILLING_BANK_ACCOUNT_NAME` | Ethiogen PLC | Manual bank details |
| `BILLING_BANK_ACCOUNT_NUMBER` | `1000123456789012` | Manual bank details |
| `BILLING_TELEBIRR_PHONE` | `+251911000000` | Manual Telebirr details |
| `BILLING_TELEBIRR_NAME` | Ethiogen PLC | Manual Telebirr details |
| `BILLING_PAYMENT_INSTRUCTIONS` | empty | Extra instructions for manual payers |

### Chapa

| Variable | Default | Purpose |
|---|---|---|
| `CHAPA_PUBLIC_KEY` | empty | Public key |
| `CHAPA_SECRET_KEY` | empty | Secret key; blank = manual-only mode |
| `CHAPA_API_BASE` | `https://api.chapa.co/v1` | API base |
| `CHAPA_AUTO_APPROVE` | `1` | `1` activates immediately on a successful webhook; `0` sends to review |

The resolved webhook is:

```
<site_url>/billing/chapa/webhook/
```

unless `chapa_webhook_url` is set in the admin row.

### Telebirr gateway (optional)

| Variable | Purpose |
|---|---|
| `TELEBIRR_API_BASE` | Gateway base URL; blank = manual transfer only |
| `TELEBIRR_API_KEY` | Gateway key |
| `TELEBIRR_MERCHANT_ID` | Merchant ID |

Telebirr has no universal public merchant API. If you use an aggregator or bank gateway, point the base URL at it. Otherwise leave it blank and use manual transfer with receipt upload.

### Facebook Page (optional)

| Variable | Purpose |
|---|---|
| `FACEBOOK_PAGE_ID` | Numeric page ID |
| `FACEBOOK_PAGE_NAME` | Display name |
| `FACEBOOK_PAGE_ACCESS_TOKEN` | Page access token (not the app secret) |
| `FACEBOOK_API_VERSION` | Graph API version, default `v21.0` |
| `FACEBOOK_DEFAULT_LINK` | Fallback link when a post has no `source_url` |

The admin row can override all of these.

### Scraper credentials (optional)

| Variable | Purpose |
|---|---|
| `ETHIOGEN_SCRAPER_URL` | Scraper endpoint |
| `ETHIOGEN_SELECTOR` | CSS selector |
| `ETHIOGEN_BACKEND_URL` | Backend base URL |
| `ETHIOGEN_API_KEY` | API key |
| `MERKATO_EMAIL` / `MERKATO_PASSWORD` | 2merkato login for tender scraping |

## 3. Admin settings sections

Open `/admin/settings/`. Each card saves independently.

### Telegram Bot & Connection

Use this to rotate the token, move to a different channel, or change the admin allow-list. After saving, restart the bot only if it does not pick up the change within 30 seconds (it normally does).

Requirements:

- The bot must be an **administrator** of the channel/group.
- The channel ID is usually a negative number such as `-1003795541703`.
- Admin IDs are Telegram **user** IDs, not usernames.

### Miniapp & Site

- `site_url` — public URL used to build absolute links.
- `notes` — free-form internal notes.

### Chapa

- Enable only when a secret key is present.
- Auto-approve is convenient but removes the manual review step.
- Register the webhook URL in the Chapa dashboard.

### Telebirr

- `telebirr_name` and `telebirr_phone` are shown to users for manual transfer.
- Gateway fields are optional and only used if a gateway base URL is set.

### Bank

- Enable/disable the bank option.
- Set the bank name, account name, and account number exactly as users should see them.

### Subscription

- Currency, price, duration, and payment instructions.
- Changes affect **new** subscriptions; existing rows keep their recorded amount and duration.

### Branding

- Wordmark, caption visibility, and logo height.
- Upload `logo_image` and `favicon_image` in `/django-admin/billing/integrationsettings/`.
- When no logo is uploaded, templates fall back to static assets:
  - `/static/branding/ethiogen-logo.png`
  - `/static/branding/favicon.png`

### Facebook

- Enable only when a page ID and page access token are set.
- Generate the page token with `GET /me/accounts?fields=id,name,access_token` in the Graph API Explorer.
- Never paste the app secret here.

## 4. Diagnostics panel

`/admin/settings/` renders `config.configuration_report()`. Each row shows a label, an ok/fail flag, and a detail string. It makes **no network calls**. It reports:

- Configuration source (admin row vs environment)
- Telegram token, channel ID, bot username, group ID, admin IDs
- Chapa live/auto-approve/webhook
- Telebirr transfer and gateway state
- Bank transfer state
- Subscription price/duration
- Site URL
- Logo upload state
- Facebook page state and API version

For live checks use:

```bash
python manage.py verify_telegram
```

## 5. External service setup

### Telegram bot

1. Create a bot with **@BotFather** and copy the token.
2. Create a channel (or use an existing one).
3. Add the bot as an administrator with permission to post.
4. Get the numeric channel ID (forward a message to a helper bot, or use `getUpdates` after posting).
5. Set the token and channel ID in `.env` or `/admin/settings/`.
6. Add your Telegram user ID to `telegram_admin_ids` / `ETHIOGEN_ADMIN_IDS`.
7. Start `bot/bot.py` or `start_bot.sh`.
8. Optionally register a webhook to `/telegram-webhook/` instead of polling.

### Telegram mini app

The mini app shell is served at `/miniapp/`. It authenticates with `initData` posted to `/billing/auth/telegram/`, which verifies the HMAC using the bot token and logs the matching Django user in.

If the mini app is served from a different origin:

```dotenv
CORS_ALLOWED_ORIGINS=https://app.example.com
CSRF_TRUSTED_ORIGINS=https://app.example.com
```

Both must be set for cross-origin POSTs to succeed.

### Chapa

1. Create a Chapa account and obtain public/secret keys.
2. In Chapa, set the webhook to `https://your-domain/billing/chapa/webhook/`.
3. Enter the keys in `/admin/settings/` → Chapa.
4. Decide whether `chapa_auto_approve` is on.
5. Test with a small amount.

### Facebook Page

1. Create a Facebook app with the Pages API.
2. Generate a page access token.
3. Enter the page ID, token, and API version in `/admin/settings/` → Facebook.
4. Publish a channel post and inspect `facebook_posted`, `facebook_post_id`, and `facebook_error` in `/django-admin/billing/channelpost/`.

## 6. Branding assets

| Asset | Where |
|---|---|
| Main logo | `IntegrationSettings.logo_image` (upload in raw admin) |
| Favicon | `IntegrationSettings.favicon_image` (fallback to logo) |
| Static fallback logo | `static/branding/ethiogen-logo.png` |
| Static fallback favicon | `static/branding/favicon.png` |
| Wordmark text | `IntegrationSettings.logo_wordmark` |
| Rendered height | `IntegrationSettings.logo_height_px` |

Template tags in `billing/templatetags/ethiogen_tags.py` expose `{% logo_url %}`, `{% favicon_url %}`, and related helpers.

## 7. Security-sensitive settings

These values are currently in `job_portal/settings.py` and should be moved to `.env` and rotated before production:

| Setting | Risk |
|---|---|
| `EMAIL_HOST_PASSWORD` | SMTP credential committed in source |
| `SECRET_KEY` fallback | Development-only fallback; set `DJANGO_SECRET_KEY` |
| `RECAPTCHA_PUBLIC_KEY` / `RECAPTCHA_PRIVATE_KEY` | Test keys; replace with production keys |
| `SILENCED_SYSTEM_CHECKS = ['captcha.recaptcha_test_key_error']` | Hides test-key warnings; remove once real keys are set |
| `ssl._create_default_https_context = ssl._create_unverified_context` | Disables certificate verification globally; remove for production |

Recommended production hardening:

```dotenv
DJANGO_DEBUG=0
DJANGO_SECRET_KEY=<long-random-value>
DJANGO_ALLOWED_HOSTS=ethiogen.com,www.ethiogen.com
CORS_ALLOWED_ORIGINS=https://app.ethiogen.com
CSRF_TRUSTED_ORIGINS=https://ethiogen.com,https://www.ethiogen.com
```

Also review:

- `SECURE_SSL_REDIRECT`
- `SESSION_COOKIE_SECURE`
- `CSRF_COOKIE_SECURE`
- `SECURE_HSTS_SECONDS`
- `SECURE_CONTENT_TYPE_NOSNIFF`

These are not enabled in `settings.py` by default. Add them behind an environment flag for production.

## 8. Configuration checklist

| Item | Where | Done |
|---|---|---|
| `DJANGO_SECRET_KEY` set | `.env` | ☐ |
| `DJANGO_DEBUG=0` | `.env` | ☐ |
| Real `DJANGO_ALLOWED_HOSTS` | `.env` | ☐ |
| Database selected and migrated | `.env` + `migrate` | ☐ |
| Telegram token + channel ID | admin or `.env` | ☐ |
| Bot is channel admin | Telegram | ☐ |
| Telegram admin IDs | admin or `.env` | ☐ |
| Chapa keys + webhook | admin + Chapa | ☐ |
| Bank/Telebirr details | admin | ☐ |
| Subscription price/duration | admin | ☐ |
| Logo + favicon uploaded | raw admin | ☐ |
| Facebook page (optional) | admin | ☐ |
| CORS/CSRF origins (mini app) | `.env` | ☐ |
| Static files collected | `collectstatic` | ☐ |
| Email credentials moved out of source | `.env` | ☐ |
| Live Telegram check | `verify_telegram` | ☐ |
