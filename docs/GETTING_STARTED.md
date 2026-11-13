# Getting Started

This guide takes a clean machine to a running Ethiogen instance and explains the first things to check after login.

## 1. Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.12 or newer | Django 6 requires Python 3.12+; the project is developed on 3.13/3.14 |
| pip | Current | Ships with Python |
| Git | Any recent | Optional, for version control |
| SQLite | Bundled | Default database, no service needed |
| PostgreSQL | 14+ | Optional; see [POSTGRES.md](POSTGRES.md) |
| Node.js | Not required | The front-end uses prebuilt CSS, not a build step |

Optional tooling is listed in `requirements-optional.txt` (Whisper transcription, Playwright scraping, watchdog, document exporters). You do **not** need it to run the web app.

## 2. Clone or open the project

```powershell
cd "E:\software project\django projects\syoapps\Vantora Catalogue\Vantora Ethiogen Job Seeker Hub"
```

If starting from Git:

```powershell
git clone https://github.com/3ecomputers-boop/ethiogen.git
cd ethiogen
```

## 3. Create a virtual environment

**Windows (PowerShell):**

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If PowerShell blocks activation:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
```

**Linux/macOS:**

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Why PyMySQL and psycopg?

- `PyMySQL` is registered as `MySQLdb` in `job_portal/__init__.py`, avoiding a C toolchain on Windows.
- `psycopg[binary]` provides prebuilt PostgreSQL wheels.
- `Pillow` is a **core** requirement because several models use `ImageField`; Django system checks fail without it.

## 4. Configure the environment

Copy the template and edit it:

```powershell
Copy-Item .env.example .env
```

```bash
cp .env.example .env
```

Minimum local values:

```dotenv
DJANGO_DEBUG=1
DJANGO_SECRET_KEY=dev-only-change-me
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
DB_ENGINE=sqlite

TELEGRAM_BOT_TOKEN=
TELEGRAM_CHANNEL_ID=
BILLING_SITE_URL=http://127.0.0.1:8000
```

Notes:

- `DJANGO_DEBUG` defaults to **off**. Without `DJANGO_DEBUG=1`, tracebacks are hidden and static files must be collected.
- `DJANGO_ALLOWED_HOSTS` is comma-separated. `*` is accepted but unsafe in production.
- `TELEGRAM_BOT_TOKEN` and `ETHIOGEN_BOT_TOKEN` are both accepted; the bot also reads the token from the admin settings row (which takes precedence).
- Never commit `.env`. It is already in `.gitignore`.

See [CONFIGURATION.md](CONFIGURATION.md) for the full variable reference.

## 5. Initialize the database

```powershell
python manage.py migrate
```

This applies migrations for all apps, including `accounts`, `jobs`, `billing`, `tenants`, `dashboard`, `social`, `recruitment`, `freelancer`, `employers`, and `borker_network`.

Check the result:

```powershell
python manage.py showmigrations
python manage.py check
```

Expected: `System check identified no issues (0 silenced).`

## 6. Create an administrator

```powershell
python manage.py createsuperuser
```

Enter a username, email, and password. Then, in the Python shell, ensure the account is staff (superusers already are):

```powershell
python manage.py shell
```

```python
from django.contrib.auth import get_user_model
User = get_user_model()
u = User.objects.get(username="your-username")
u.is_staff = True
u.is_superuser = True
u.is_verified = True
u.save()
exit()
```

> Existing installations may already have an `admin` account. Use `manage.py changepassword admin` to reset a forgotten password instead of creating a duplicate.

## 7. Run the development server

```powershell
python manage.py runserver 127.0.0.1:8000
```

Open:

- Public site — <http://127.0.0.1:8000/>
- Login — <http://127.0.0.1:8000/accounts/login/>
- Custom admin — <http://127.0.0.1:8000/admin/>
- Raw Django admin — <http://127.0.0.1:8000/django-admin/>
- Social feed — <http://127.0.0.1:8000/social/>

## 8. First login and orientation

After signing in as staff:

1. **`/admin/`** — confirm the KPI cards load (users, job seekers, subscriptions, revenue).
2. **`/admin/settings/`** — open Configuration and check the diagnostics panel.
3. **`/admin/admin-models/`** — confirm every registered model appears with a count and a link.
4. **`/django-admin/`** — confirm the raw admin loads with its CSS (this validates static file serving).
5. **`/social/`** — create a test post, like it, and add a comment.
6. **`/billing/analytics/`** — confirm the JSON response for staff.

Login redirect behaviour is role-aware:

- Staff → `/construction/` (the construction workforce dashboard) if no `next` is supplied. Staff can then use `/admin/` for the custom console.
- Job seeker with an unverified profile → OTP verification.
- Job seeker with a verified profile → job seeker dashboard.
- Client/employer → employer dashboard.
- No profile → client profile setup.

`LOGIN_URL` is `/accounts/login/` and `LOGIN_REDIRECT_URL` is `/admin/`. Note that the custom login view applies the role-based routing above and does not use `LOGIN_REDIRECT_URL` directly; the setting still matters for other `login_required` redirects.

## 9. Static and media files in development

`DEBUG=True` lets Django serve `/static/` and `/media/` automatically.

This project also adds an explicit static route so the custom admin stays styled when `DEBUG=False`:

```python
urlpatterns += [
    path('static/<path:path>', serve, {'document_root': BASE_DIR / 'static'}),
]
```

For production, prefer `collectstatic` plus a web-server mapping. See [DEPLOYMENT.md](DEPLOYMENT.md).

## 10. Optional: start the Telegram bot

The bot is a separate process from the web server:

```bash
# Linux/macOS
./start_bot.sh
```

```powershell
# Windows
.\venv\Scripts\python.exe bot\bot.py
```

Before starting it:

1. Put a real token in `.env` **or** in Configuration → Telegram.
2. Add the bot as an administrator of the target channel.
3. Set `TELEGRAM_CHANNEL_ID` to the numeric channel ID (e.g. `-1003795541703`).
4. Add your Telegram user ID to `ETHIOGEN_ADMIN_IDS` to use admin commands.

Verify connectivity:

```powershell
python manage.py verify_telegram
python manage.py simulate_bot
```

`verify_telegram` performs live network calls. If `api.telegram.org` is unreachable in your environment, it will fail even when the token is correct; `simulate_bot` works offline and exercises the inline-button handlers.

## 11. Day-one smoke test

```powershell
python manage.py check
python manage.py simulate_bot
python manage.py verify_telegram --publish   # requires network
```

Then, in the browser:

| Check | Expected |
|---|---|
| `/admin/` loads with sidebar and KPI cards | Styled, responsive layout |
| Sidebar collapses on a narrow window | Hamburger menu works |
| `/admin/settings/` saves a section | Success message, values persist |
| `/admin/admin-models/` lists models | Counts and links render |
| `/social/` post/like/comment | Feed updates |
| `/social/connections/` | Pending and accepted lists render |
| `/social/notifications/` | Unread items are highlighted on first load |
| `/billing/analytics/` | JSON with subscription and revenue counts |

## 12. Common first-run problems

| Symptom | Likely cause | Fix |
|---|---|---|
| `UnicodeEncodeError` on Windows | Console encoding | Run `chcp 65001`, or use the fixed management commands |
| Admin page unstyled | `DEBUG=False` and no static mapping | Set `DJANGO_DEBUG=1` for local work, or run `collectstatic` and configure the web server |
| `no such table` | Migrations not applied | `python manage.py migrate` |
| `CSRF verification failed` | Missing cookie/referer in a scripted login | Use a session that first GETs the login page, or use the browser |
| Telegram calls time out | Network blocked | Use `simulate_bot`; test Telegram from the production host |
| `Pillow` import error | Optional install skipped | `pip install -r requirements.txt` |
| `Cannot use ImageField because Pillow is not installed` | Same | Install Pillow |

More in [TROUBLESHOOTING.md](TROUBLESHOOTING.md).
