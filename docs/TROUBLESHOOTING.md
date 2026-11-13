# Troubleshooting

This page collects the errors most likely to appear during setup and operation, with the shortest reliable fix.

## Quick diagnostics

```bash
python manage.py check
python manage.py showmigrations
python manage.py migrate --plan
python manage.py simulate_bot
python manage.py verify_telegram
```

Useful shell checks:

```python
from django.contrib.auth import get_user_model
User = get_user_model()
User.objects.filter(is_staff=True).values_list("username", "is_superuser")
```

---

## Installation and environment

### `ModuleNotFoundError: No module named 'django'`

The virtualenv is not active or dependencies were not installed.

```powershell
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Confirm the interpreter:

```powershell
python -c "import sys; print(sys.executable)"
```

### `Pillow` / `ImageField` errors

`Pillow` is a core requirement because several models use `ImageField`.

```bash
pip install -r requirements.txt
```

### `ImproperlyConfigured` or missing `.env` values

Copy the template:

```bash
cp .env.example .env
```

`settings.py` calls `load_dotenv()` from the project root. Run `manage.py` from the directory that contains `.env`.

### `UnicodeEncodeError` on Windows

Some management commands print Unicode symbols/emoji that the default console encoding cannot encode.

Options:

```powershell
chcp 65001
$env:PYTHONIOENCODING = "utf-8"
```

or set the environment variable permanently:

```powershell
[Environment]::SetEnvironmentVariable("PYTHONIOENCODING", "utf-8", "User")
```

The known Telegram command in this project has already been fixed, but other scripts may still emit Unicode.

### PowerShell blocks `Activate.ps1`

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
```

---

## Database and migrations

### `no such table: ...`

Migrations were not applied:

```bash
python manage.py migrate
```

If you added an app, confirm it is in `INSTALLED_APPS` and has `migrations/__init__.py`.

### `You have N unapplied migration(s)`

Run `migrate`. If the app is new:

```bash
python manage.py makemigrations <app>
python manage.py migrate <app>
```

### `django.db.utils.OperationalError: database is locked` (SQLite)

SQLite allows one writer at a time. The project sets a 20-second timeout, but heavy concurrency still conflicts.

Fixes:

- Stop the bot/cron during schema changes.
- Reduce concurrent writes.
- Move to PostgreSQL for production.

### PostgreSQL connection refused

Check:

```bash
python -c "import psycopg; print(psycopg.__version__)"
```

and the `DB_*` variables. Confirm the service is running and the role can connect:

```bash
psql -h 127.0.0.1 -U ethiogen -d ethiogen
```

See [POSTGRES.md](POSTGRES.md).

### Migration applied to the wrong database

`DB_ENGINE` decides the database. If you migrated SQLite but the app uses PostgreSQL, the tables exist in the wrong place. Check `.env` and `settings.DATABASES`.

---

## Login and permissions

### `/admin/` redirects to login in a loop

- Confirm the user is staff:

```python
u = get_user_model().objects.get(username="admin")
u.is_staff = True
u.is_active = True
u.save()
```

- Confirm `LOGIN_URL` is `/accounts/login/`.
- Clear stale session cookies.

### `CSRF verification failed` in a scripted login

Django requires the CSRF cookie and token. A raw POST without first GETting the form fails. In scripts:

1. GET the login page with a cookie jar.
2. Extract `csrfmiddlewaretoken`.
3. POST with the same session and a `Referer` header.

The browser flow does this automatically.

### Password reset / forgotten admin password

```bash
python manage.py changepassword admin
```

If the account does not exist, create it:

```bash
python manage.py createsuperuser
```

### `403 Forbidden` on `/django-admin/`

The user is authenticated but lacks staff/superuser status, or model permissions. Grant `is_staff` and the relevant permissions, or use a superuser.

### Login redirects to the wrong dashboard

`accounts.views._resolve_dashboard` routes by profile:

- Staff → `jobs:construction_dashboard`
- Unverified seeker → OTP page
- Verified seeker → seeker dashboard
- Client → employer dashboard
- No profile → client profile setup

Use an explicit `?next=/admin/` if you need a specific destination after login.

---

## Static files and styling

### Admin or dashboard is unstyled

Causes:

1. `DEBUG=False` and the web server is not serving `/static/`.
2. `collectstatic` was never run.
3. The static URL is wrong or blocked.

Fixes:

```bash
python manage.py collectstatic --noinput
```

Then map `/static/` to `staticfiles/` at the web server.

For local work, set `DJANGO_DEBUG=1` so Django serves static files automatically. The project also has an explicit `/static/<path>` route that serves from `static/` even when `DEBUG=False`.

Verify:

```bash
curl -I http://127.0.0.1:8000/static/css/tailwind.css
```

Expect `200` and `text/css`.

### Bootstrap Icons do not render

The icon font is loaded from jsDelivr. A blocked CDN, CSP, or offline environment leaves empty squares. Either allow the CDN or vendor the font locally.

### CSS changes do not appear

- Hard-refresh (Ctrl+F5).
- If serving `staticfiles/`, re-run `collectstatic`.
- Check for a stale service worker or proxy cache.

### Admin template overrides are ignored

Django's app-directories loader reaches `django/contrib/admin/templates` before app templates when `django.contrib.admin` is first in `INSTALLED_APPS`. This project puts `admin_templates/` in `TEMPLATES['DIRS']` so overrides win. Put overrides there, not in an app's `templates/` directory.

---

## URLs and routing

### `NoReverseMatch`

A `{% url %}` name does not exist or the namespace is wrong.

```bash
python manage.py check_url_references
```

Common causes:

- Missing namespace (`dashboard:home` vs `home`).
- A URL removed but still referenced in a template.
- The app is not in `INSTALLED_APPS`.

### `urls.W005: URL namespace 'jobs' isn't unique`

Do not include `jobs.urls` twice **with** a namespace. The root includes it without a namespace; `employers.urls` owns the `jobs` namespace. Preserve that arrangement.

### `/admin/` shows the old Django admin

- `/admin/` is the custom dashboard (`dashboard.urls`).
- `/django-admin/` is the raw admin.
- `/admin/dashboard/` is the legacy `staff_dashboard` view.

If `/admin/` shows Django admin, check the order in `job_portal/urls.py`; `path('admin/', include('dashboard.urls'))` must be present and `django-admin/` must come before it only if it uses a distinct prefix.

### `/social/` 404s

Confirm:

1. `social` is in `INSTALLED_APPS`.
2. `path('social/', include('social.urls'))` is in the root URLconf.
3. The app has `urls.py` and `app_name = 'social'`.

---

## Telegram and bot

### `api.telegram.org` times out

The host cannot reach Telegram. This is common in restricted networks. Use:

```bash
python manage.py simulate_bot
```

and run live checks from the production host.

### `TELEGRAM_BOT_TOKEN is not configured`

Set the token in **either**:

- `/admin/settings/` → Telegram, or
- `.env` as `TELEGRAM_BOT_TOKEN` / `ETHIOGEN_BOT_TOKEN`.

The admin row takes precedence.

### `TELEGRAM_CHANNEL_ID is not configured`

Set `telegram_channel_id` in the admin row, or `ETHIOGEN_UPDATE_GROUP_ID` in `.env` (this populates `settings.TELEGRAM_CHANNEL_ID`). `TELEGRAM_CHANNEL_ID` in `.env` alone is not read by `settings.py`.

### `chat not found`

- Wrong numeric ID.
- The bot is not a member of the channel.
- The channel is private and the bot lacks access.

Use a negative ID such as `-1003795541703`, not the `@username`, unless the channel is public.

### `CHAT_ADMIN_REQUIRED`

Promote the bot to administrator with permission to post messages and manage the channel.

### `verify_telegram` fails at the admin check

The token is valid and the chat is reachable, but the bot is not an administrator. Fix the channel permissions.

### Bot starts but does nothing

- Another process is polling the same token (only one poller allowed).
- A webhook is registered; polling then returns conflicts. Delete the webhook or stop polling.
- Check `bot.log` for `Conflict: terminated by other getUpdates request`.

### Receipt upload says unavailable

`get_bot()` returned `None`. Confirm the token is configured and the bot object initialized. Check the log for the underlying exception.

### Alerts are not sent

Check:

1. Subscription is `active` and not expired.
2. `telegram_chat_id` is set (or a `TelegramProfile` exists).
3. `alerts_muted` is false.
4. `alert_mode` is `immediate` or `matched` (digest uses `send_digest`).
5. No successful `AlertDelivery` already exists for that `(subscription, post)`.
6. The bot can DM the user (users must have started the bot).

---

## Payments

### Chapa checkout fails

- Secret key missing or wrong.
- `CHAPA_API_BASE` incorrect.
- The account is not enabled for the currency/amount.
- Network/firewall blocks `api.chapa.co`.

Check the application log for the Chapa response message.

### Chapa webhook returns 200 but nothing activates

- `chapa_auto_approve` is off → review manually.
- The payload status is not `success`.
- The reference cannot be mapped to a subscription.
- The webhook URL is wrong or Chapa cannot reach the host.

Inspect logs and the subscription's `chapa_reference` / `chapa_payload`.

### Manual payment approved but the user got no DM

`resolve_chat_id` found no Telegram chat ID, or Telegram rejected the send. Approval still succeeds; check `TelegramProfile` and the log.

---

## Social features

### Feed is empty

Create a post or seed one. The feed is global and shows the latest 50 posts.

### Like does not toggle

`like_post` is a GET route. If a browser prefetches links, likes can toggle unexpectedly. Use a normal click; hardening to POST is on the backlog.

### Connection request missing

- `Connection` is unique per `(from_user, to_user)`.
- A→B and B→A are separate rows.
- Only the recipient can accept/reject.

### Inbox send fails with 404

The recipient field expects a **numeric user ID**, not a username. Look up the ID in `/django-admin/accounts/user/`.

### Notifications are already read

Opening `/social/notifications/` marks all unread rows as read. This is intentional in the current implementation.

---

## Dashboard

### KPI counts look wrong

Counts are live `COUNT(*)` queries per page load. If a model was added without registering it, or a table is empty, the card reflects that. Confirm in `/django-admin/`.

### Approve/Reject button returns 403

The form is POST-only and requires CSRF. Ensure the page was loaded from the dashboard (not a cached copy missing the token) and the user is staff.

### "All Models" link 404s

The raw admin URL is `/django-admin/<app_label>/<model_name>/`. If a model is registered under a custom admin site or not registered at all, it will not appear. Check `admin.site._registry`.

### Settings save says success but values do not change

- The section name must match `SECTION_FIELDS` in `dashboard/views.py`.
- Checkbox fields are only saved when posted as `on`/`1`/`true`.
- The config cache is invalidated on save; if another process cached the old row, it refreshes within 30 seconds.

---

## Email

### Emails are not delivered

`settings.py` uses SMTP over SSL on port 465. Verify:

```bash
python manage.py sendtestemail you@example.com
```

Check:

- Host/port/SSL settings.
- Credentials (currently in `settings.py`; move to `.env`).
- Provider blocks/port restrictions.
- SPF/DKIM for deliverability.

Email failures are logged but never break the subscription or application flow.

### `ssl` certificate errors

`settings.py` currently disables certificate verification globally:

```python
ssl._create_default_https_context = ssl._create_unverified_context
```

Remove this in production and fix the underlying CA trust instead.

---

## Performance

### Pages are slow with large tables

- Add indexes for frequent filters.
- Cache dashboard counts.
- Paginate list endpoints.
- Use `select_related`/`prefetch_related` (many views already do).
- Move alert fan-out and scraping off the request path.

### Bot is slow or hits flood control

Telegram limits bulk sends. The alert code inserts a small delay and de-duplicates, but large lists still take time. Batch or queue the fan-out if you exceed a few hundred recipients per post.

---

## Django/Python compatibility

### `AttributeError: 'super' object has no attribute 'dicts'` on Python 3.14

This is a Django 5.1 incompatibility with Python 3.14. The project pins Django `>=6.0.9,<6.1`. Upgrade Django within that range and recreate the virtualenv if necessary.

### `format_html()` errors after upgrading

Django 6 removed the no-argument form of `format_html()`. Use `mark_safe()` for static markup and `format_html(.., ..)` with arguments for interpolation. The codebase has already been updated; new code should follow the same pattern.

---

## Getting more information

- Run `python manage.py check --deploy` for production warnings.
- Set `DJANGO_DEBUG=1` locally to see tracebacks.
- Check the terminal running `runserver`, plus `bot.log`, `cron` logs, and the web server error log.
- Use `python manage.py shell` to inspect objects directly.
- For static issues, use the browser Network tab and `curl -I`.
- For Telegram issues, run `verify_telegram` from the same host as production.
- For payment issues, inspect `Subscription.chapa_payload`, `review_note`, and the Chapa dashboard logs.

## Before filing a bug

Collect:

1. The exact command or URL.
2. The full traceback or HTTP status.
3. `python manage.py check` output.
4. Relevant settings (redact secrets).
5. Whether it reproduces with `simulate_bot` vs live Telegram.
6. Database engine and Python/Django versions.
