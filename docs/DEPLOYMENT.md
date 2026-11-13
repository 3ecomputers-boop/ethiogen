# Deployment

This guide covers a production deployment of the Django web process and the Telegram bot. It targets a single Linux/cPanel host first, with notes for a conventional reverse-proxy setup.

## 1. Deployment shapes

| Shape | Web | Bot | Database |
|---|---|---|---|
| Minimal | `runserver` behind a firewall (not recommended) | `bot/bot.py` | SQLite |
| cPanel/Passenger/WSGI | `passenger_wsgi.py` or mod_wsgi | long-running process | PostgreSQL preferred |
| Reverse proxy | Gunicorn/uWSGI + Nginx | systemd service | PostgreSQL |
| Container | Gunicorn + ASGI/WSGI container | second container | managed PostgreSQL |

For anything beyond a demo, use PostgreSQL and a real web server.

## 2. Pre-deployment checklist

```bash
python manage.py check --deploy
python manage.py migrate --plan
python manage.py collectstatic --noinput
python manage.py verify_telegram --publish --delete-after
```

Also verify:

- [ ] `DJANGO_DEBUG=0`
- [ ] `DJANGO_SECRET_KEY` is long, random, and unique
- [ ] `DJANGO_ALLOWED_HOSTS` lists real hostnames
- [ ] Database is backed up
- [ ] `CORS_ALLOWED_ORIGINS` / `CSRF_TRUSTED_ORIGINS` are explicit (if using the mini app cross-origin)
- [ ] Telegram token and channel are configured and tested
- [ ] Chapa webhook is registered
- [ ] Static files are collected and served
- [ ] Media is writable and backed up
- [ ] Bot process is supervised
- [ ] Cron jobs are installed
- [ ] Email credentials are moved out of source and tested (`sendtestemail`)

## 3. Environment

Create `.env` on the server (never commit it):

```dotenv
DJANGO_DEBUG=0
DJANGO_SECRET_KEY=<long-random-value>
DJANGO_ALLOWED_HOSTS=ethiogen.com,www.ethiogen.com

DB_ENGINE=postgresql
DB_NAME=ethiogen
DB_USER=ethiogen
DB_PASSWORD=<strong-password>
DB_HOST=127.0.0.1
DB_PORT=5432
DB_SSLMODE=prefer

BILLING_SITE_URL=https://ethiogen.com
CORS_ALLOWED_ORIGINS=https://app.ethiogen.com
CSRF_TRUSTED_ORIGINS=https://ethiogen.com,https://www.ethiogen.com

TELEGRAM_BOT_TOKEN=<token>
ETHIOGEN_UPDATE_GROUP_ID=-100...
ETHIOGEN_CHANNEL_USERNAME=ethiogenjob
ETHIOGEN_ADMIN_IDS=123456789

CHAPA_PUBLIC_KEY=<key>
CHAPA_SECRET_KEY=<secret>
CHAPA_AUTO_APPROVE=1
```

Set restrictive file permissions:

```bash
chmod 600 .env
```

## 4. Database: PostgreSQL

A detailed migration guide already exists in [POSTGRES.md](POSTGRES.md). Summary:

1. Create the role and database (see `tools/pg_bootstrap.py`).
2. Set the `DB_*` variables.
3. Preview the migration:

```bash
python tools/migrate_to_postgres.py
```

4. Run it:

```bash
python tools/migrate_to_postgres.py --apply
# if the target already has app data:
python tools/migrate_to_postgres.py --apply --allow-existing
```

5. Start the app against PostgreSQL and run `python manage.py check`.

Keep the SQLite file as a rollback copy until the PostgreSQL deployment is verified.

## 5. Static and media files

### Collect static

```bash
python manage.py collectstatic --noinput
```

Output: `staticfiles/`.

`STORAGES` uses `StaticFilesStorage` (no hashed names), so file names stay predictable across deploys.

### Web-server mapping

**Nginx example:**

```nginx
location /static/ {
    alias /home/syorelig/ethiogen/job_portal/staticfiles/;
    expires 1y;
    add_header Cache-Control "public, immutable";
}

location /media/ {
    alias /home/syorelig/ethiogen/job_portal/media/;
    expires 7d;
}
```

**Apache/LiteSpeed:** the repository `.htaccess` already contains a rule:

```apache
RewriteRule ^static/(.*)$ /home/syorelig/ethiogen/job_portal/staticfiles/$1 [L]
```

Update the absolute path for your server. The `.htaccess` also disables `.env` and `*.sqlite3` access and sets basic security headers.

If you cannot map `/static/` at the web server, the project's explicit Django route (`/static/<path>` → `static/`) will still serve source assets. This is a fallback, not a performance solution.

### Media uploads

`media/` must be writable by the web and bot processes. Receipts go to `media/billing/receipts/`. In production, prefer serving receipts through an authenticated view or private storage rather than exposing all of `media/` publicly.

## 6. WSGI/ASGI

`job_portal/wsgi.py` exposes `application`. Example Gunicorn:

```bash
gunicorn job_portal.wsgi:application \
  --bind 127.0.0.1:8001 \
  --workers 3 \
  --timeout 60 \
  --access-logfile logs/gunicorn.access.log \
  --error-logfile logs/gunicorn.error.log
```

Example Nginx proxy:

```nginx
server {
    listen 443 ssl http2;
    server_name ethiogen.com www.ethiogen.com;

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Set `USE_X_FORWARDED_HOST`/`SECURE_PROXY_SSL_HEADER` if you terminate TLS at the proxy and rely on `request.is_secure()`.

### cPanel

Typical layout:

```
/home/<user>/ethiogen/job_portal/        project root (manage.py)
/home/<user>/virtualenv/ethiogen/3.13/   virtualenv
```

Use the cPanel Python app / Passenger configuration to point at `job_portal.wsgi:application`, or the mod_wsgi block in `.htaccess`. Ensure:

- The virtualenv path matches the server.
- `DJANGO_SETTINGS_MODULE=job_portal.settings`.
- `.env` is readable by the app user.
- `staticfiles/` and `media/` are readable/writable as appropriate.
- LiteSpeed caching is disabled for `/telegram-webhook/` (the `.htaccess` already does this).

## 7. Telegram bot process

The bot is long-running and must be supervised.

### Option A: `start_bot.sh`

```bash
chmod +x start_bot.sh
./start_bot.sh
```

It loads `.env`, refuses to start without `TELEGRAM_BOT_TOKEN`, writes `bot.pid`, and logs to `bot.log`. Update `PROJECT_DIR` and `VENV_PYTHON` at the top of the script for your host.

### Option B: systemd

```ini
[Unit]
Description=Ethiogen Telegram bot
After=network.target

[Service]
Type=simple
User=syorelig
WorkingDirectory=/home/syorelig/ethiogen/job_portal
EnvironmentFile=/home/syorelig/ethiogen/job_portal/.env
ExecStart=/home/syorelig/virtualenv/ethiogen/3.13/bin/python bot/bot.py
Restart=always
RestartSec=5
StandardOutput=append:/home/syorelig/ethiogen/job_portal/bot.log
StandardError=append:/home/syorelig/ethiogen/job_portal/bot.log

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now ethiogen-bot
sudo systemctl status ethiogen-bot
```

### Polling vs webhook

- `bot/bot.py` uses `run_polling()`.
- If you switch to the webhook at `/telegram-webhook/`, stop the polling process and call `setWebhook` once. Never run both.

## 8. Scheduled jobs

Install cron entries for digest and reminders (see [MANAGEMENT_COMMANDS.md](MANAGEMENT_COMMANDS.md)):

```cron
0 * * * * cd /home/syorelig/ethiogen/job_portal && venv/bin/python manage.py send_digest >> logs/digest.log 2>&1
0 6 * * * cd /home/syorelig/ethiogen/job_portal && venv/bin/python manage.py renewal_reminders --days 3 >> logs/reminders.log 2>&1
```

Optional:

```cron
*/30 * * * * cd /home/syorelig/ethiogen/job_portal && venv/bin/python manage.py post_website_update --url "$SCRAPER_URL" --groups "$CHANNEL_ID" >> logs/scraper.log 2>&1
0 7 * * * cd /home/syorelig/ethiogen/job_portal && venv/bin/python manage.py scrape_tenders --groups "$CHANNEL_ID" >> logs/tenders.log 2>&1
```

Ensure `logs/` exists and is writable.

## 9. Security hardening

Add these in production (ideally behind an env flag so local development stays simple):

```python
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
```

Also:

- Remove `ssl._create_default_https_context = ssl._create_unverified_context` from `settings.py`; it disables certificate verification globally.
- Move `EMAIL_HOST_PASSWORD`, reCAPTCHA keys, and any other secrets out of `settings.py` into `.env`.
- Replace reCAPTCHA test keys and remove `SILENCED_SYSTEM_CHECKS = ['captcha.recaptcha_test_key_error']`.
- Restrict `/admin/` and `/django-admin/` to staff and consider IP allow-listing or a VPN.
- Use a strong `DJANGO_SECRET_KEY`; rotating it invalidates sessions.
- Keep `DEBUG=0`; never deploy with tracebacks enabled.
- Protect `media/billing/receipts/` if receipts are sensitive.
- Review the `csrf_exempt` API endpoints and add staff guards where appropriate.
- Add rate limiting at the proxy for login, registration, and webhook routes.
- Back up the database and media regularly; test restores.

## 10. Logging and monitoring

Recommended log locations:

| Log | Location |
|---|---|
| Web server | `/var/log/nginx/*.log` or hosting panel |
| Gunicorn | `logs/gunicorn.*.log` |
| Bot | `bot.log` |
| Cron | `logs/*.log` |
| Django app | Configure a `LOGGING` dict to write to `logs/django.log` |

Health checks:

```bash
curl -I https://ethiogen.com/
curl -s -o /dev/null -w "%{http_code}\n" https://ethiogen.com/admin/
python manage.py check
python manage.py verify_telegram
```

Monitor:

- 5xx rate
- Bot process uptime
- Cron success/failure
- Telegram 429/flood-control errors
- Disk usage for `media/` and `staticfiles/`
- Database connections and slow queries

## 11. Backups

Back up:

1. PostgreSQL database (`pg_dump`) or `db.sqlite3`.
2. `media/` (receipts, logos, profile images).
3. `.env` (securely, separate from the database backup).
4. `staticfiles/` is reproducible from `static/` + collectstatic; optional.

Example:

```bash
pg_dump -Fc "$DB_NAME" > backups/ethiogen_$(date +%F).dump
tar -czf backups/media_$(date +%F).tar.gz media/
```

Retain several generations and test a restore in staging.

## 12. Rolling deploy procedure

```bash
# 1. Pull
git pull --ff-only

# 2. Install dependencies if changed
venv/bin/pip install -r requirements.txt

# 3. Back up
pg_dump -Fc "$DB_NAME" > backups/predeploy_$(date +%F_%H%M).dump

# 4. Migrate
venv/bin/python manage.py migrate --noinput

# 5. Collect static
venv/bin/python manage.py collectstatic --noinput

# 6. Check
venv/bin/python manage.py check

# 7. Restart web and bot
sudo systemctl restart ethiogen-web
sudo systemctl restart ethiogen-bot

# 8. Smoke test
curl -I https://ethiogen.com/
venv/bin/python manage.py verify_telegram
```

If migrations are not backward compatible, deploy in two phases (expand, then contract) and keep the old process running until the new one is healthy.

## 13. Scaling notes

- The session backend is the database by default; move to Redis/`cached_db` for high traffic.
- Telegram sends are synchronous HTTP calls from Django. For large subscriber lists, move alert fan-out to a queue/worker.
- The custom dashboard runs many `COUNT(*)` queries per page; cache counts if the tables grow large.
- Add database indexes based on slow-query analysis; several are already defined in models.
- Serve static/media from object storage or a CDN for global traffic.
- Use multiple Gunicorn workers; each worker has its own in-process `config` cache (30s TTL), which is fine because the database row is the source of truth.

## 14. Rollback

1. Restore the previous code revision.
2. Restore the database backup if migrations were applied.
3. `collectstatic` if templates/assets changed.
4. Restart web and bot.
5. Re-run `check` and `verify_telegram`.

Keep the previous release directory and database dump until the new release has been stable for at least one business day.
