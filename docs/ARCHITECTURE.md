# Architecture

This document explains how the Ethiogen project is assembled: the Django configuration, URL routing, request lifecycle, app boundaries, configuration resolution, and the main data relationships.

## 1. High-level picture

```
Browser / Telegram mini app / Telegram bot
                │
                ▼
        job_portal/urls.py
                │
   ┌────────────┼─────────────┬──────────────┬──────────────┐
   ▼            ▼             ▼              ▼              ▼
 public site  accounts      billing       dashboard      social
 (jobs,       (login,      (subs, posts,  (staff UI)     (feed,
  employers,   register)    payments)                     network)
  tenants)
   │            │             │              │              │
   └────────────┴─────────────┴──────┬───────┴──────────────┘
                                    ▼
                             Django ORM / SQLite/PostgreSQL
                                    │
                         ┌──────────┴──────────┐
                         ▼                     ▼
                 bot/bot.py process     management commands
                 (Telegram polling)     (cron / manual)
```

Two processes are typical in deployment:

1. **Web process** — WSGI/ASGI server running `job_portal.wsgi:application`.
2. **Bot process** — `python bot/bot.py`, long polling Telegram.

Both share the same database and the same `.env`.

## 2. Project layout

```
job_portal/
├── __init__.py        # registers PyMySQL as MySQLdb
├── settings.py        # all project settings
├── urls.py            # root URL configuration
├── wsgi.py            # WSGI entry point
└── asgi.py            # ASGI entry point

accounts/              # custom user, roles, auth templates
jobs/                  # public portal, profiles, talents, APIs, signals
billing/               # subscriptions, channel posts, integrations, payments
dashboard/             # custom staff admin console
social/                # LinkedIn-style social graph and feed
tenants/               # multi-tenant organizations and workspaces
recruitment/           # simple recruitment job board
freelancer/            # freelance jobs and bids
employers/             # employer profile module
borker_network/        # broker/deal/payout/task module
users/                 # thin app, no models
bot/                   # Telegram bot process
tools/                 # deployment/diagnostic scripts
docs/                  # documentation
templates/             # site-wide templates
static/                # source assets (CSS, JS, images)
staticfiles/           # collectstatic output
media/                 # user uploads
```

## 3. Settings (`job_portal/settings.py`)

### Loading order

1. `.env` is loaded by `python-dotenv` at import time.
2. Environment variables are read with `os.getenv`.
3. Hard-coded defaults are used as a last resort.

### Key decisions

| Setting | Value / behaviour |
|---|---|
| `AUTH_USER_MODEL` | `accounts.User` (custom user with roles) |
| `DEBUG` | Off unless `DJANGO_DEBUG` is `1/true/yes/on` |
| `ALLOWED_HOSTS` | `DJANGO_ALLOWED_HOSTS`, comma-separated, defaults to `*` |
| Database | SQLite by default; PostgreSQL when `DB_ENGINE=postgresql` |
| `STATIC_ROOT` | `staticfiles/` |
| `MEDIA_ROOT` | `media/` |
| `TEMPLATES['DIRS']` | `admin_templates/` first, so admin overrides win |
| `LOGIN_URL` | `/accounts/login/` |
| `LOGIN_REDIRECT_URL` | `/admin/` |
| Time zone | `UTC` |
| Languages | English and Amharic |
| REST framework | Session auth, `IsAuthenticated`, JSON + browsable API, 20/page |
| CORS | Deny-by-default; `CORS_ALLOWED_ORIGINS` must be explicit |
| CSRF trusted origins | `CSRF_TRUSTED_ORIGINS` must mirror CORS for cross-origin POSTs |

### Middleware order

```
corsheaders.middleware.CorsMiddleware
django.middleware.security.SecurityMiddleware
django.contrib.sessions.middleware.SessionMiddleware
django.middleware.locale.LocaleMiddleware
django.middleware.common.CommonMiddleware
django.middleware.csrf.CsrfViewMiddleware
django.contrib.auth.middleware.AuthenticationMiddleware
django.contrib.messages.middleware.MessageMiddleware
django.middleware.clickjacking.XFrameOptionsMiddleware
```

`CorsMiddleware` sits above `CommonMiddleware` so CORS headers are still attached if `CommonMiddleware` issues a redirect.

### Context processor

`tenants.context_processors.platform_admin` adds platform-wide counts for admin templates. The custom dashboard computes its own counts and does not rely on it.

### Installed apps

```
django.contrib.admin        django.contrib.auth
django.contrib.contenttypes django.contrib.sessions
django.contrib.messages     django.contrib.staticfiles
accounts                    recruitment
jobs                        freelancer
users                       employers
borker_network              billing
tenants                     dashboard
social                      django_countries
rest_framework             corsheaders
```

## 4. URL routing (`job_portal/urls.py`)

The root configuration is intentionally explicit:

| Pattern | Included/View | Notes |
|---|---|---|
| `/django-admin/` | `admin.site.urls` | Raw Django admin |
| `/admin/` | `dashboard.urls` | Custom admin console |
| `/admin/dashboard/` | `jobs.views.staff_dashboard` | Legacy operator dashboard |
| `/` | `jobs.urls` (no namespace) | Public site and JSON API |
| `/` | `accounts.urls` | `/login/`, `/logout/`, `/register/` |
| `/` | `freelancer.urls` | Freelance module |
| `/` | `employers.urls` | Employer module (also includes jobs URLs) |
| `/recruitment/` | `recruitment.urls` | Recruitment module |
| `/billing/` | `billing.urls` | Chapa webhook, analytics, employer API |
| `/tenants/` | `tenants.urls` | Workspaces, console, tenant API |
| `/social/` | `social.urls` | LinkedIn-style features |
| `/telegram-webhook/`, `/tg/wh/` | `jobs.views.telegram_webhook` | Bot webhook aliases |
| `/miniapp/` | `jobs.views.mini_app` | Telegram mini app shell |
| `/api/...` | `jobs.views.*` | Registration, login, jobs, talents, etc. |
| `/static/<path>` | `django.views.static.serve` | Explicit static serving when `DEBUG=False` |

`jobs.urls` is included without a namespace at the root **and** through `employers.urls` with the `jobs` namespace. This is deliberate: templates can use both `{% url 'home' %}` and `{% url 'jobs:home' %}`. Including it twice *with* namespaces would trigger `urls.W005`.

## 5. Request lifecycle

A typical request:

1. CORS → security → session → locale → common → CSRF → auth → messages → X-Frame-Options.
2. URL resolver picks the root pattern.
3. View runs, usually decorated with `login_required` and/or a staff check.
4. ORM queries run through the configured database.
5. View renders a template (often extending `templates/base.html` or an app-specific base) or returns `JsonResponse`.
6. Session and messages are persisted.

### Access control patterns

| Area | Guard |
|---|---|
| Public pages | None |
| Social pages | `@login_required` |
| Custom dashboard | `login_required` + `user_passes_test(is_staff)` |
| Raw Django admin | Django admin's own staff/superuser checks |
| Billing analytics | `login_required` + `is_staff` |
| Tenant operator console | Superuser |
| Employer APIs | Employer guard in `billing/employer_api.py` |
| Chapa webhook | `csrf_exempt`, POST only, no login |
| Telegram webhook | Shared-secret/URL-based, POST only |

## 6. Configuration resolution (`billing/config.py`)

Every integration value resolves in this order:

1. `IntegrationSettings` row (edited at `/admin/settings/`)
2. `settings.py` / environment variable
3. Built-in default

The row is cached for **30 seconds** (`CACHE_TTL_SECONDS`). Saving settings from the dashboard calls `config.invalidate_cache()` so the change is visible immediately to the web process; the bot picks it up within the TTL without a restart.

This is why the admin settings page is the preferred place to edit tokens: it overrides `.env` and needs no restart.

## 7. Data model overview

### Accounts and roles

```
Role (super_admin, admin, employer, job_seeker)
  ▲
  │ FK
User (AbstractUser) ── is_verified, is_suspended, last_login_ip
```

`User` is the central actor. Profiles link to it one-to-one.

### Job portal core

```
User
 ├── ClientProfile ──< Job ──< Booking
 │        │              └──< Review
 │        ├──< JobPost ──< JobApplication
 │        └──< TalentAccess >── Talent
 ├── JobSeekerProfile ──< Booking / Review / WorkerRating
 │        ├── WorkerVerification (1:1)
 │        ├── WorkerAvailability (1:1)
 │        └──< WorkerPortfolio
 ├── TelegramProfile (1:1)
 └── UserPreference (1:1)
```

Supporting catalogues: `Category`, `SubCategory`, `JobCategory`, `Profession`, `ProfessionalRate`.

Operational models: `Message`, `HireRequest`, `PostNeedRequest`, `FavoriteWorker`, `ScrapedContent`.

### Billing and distribution

```
User ──< Subscription ──< AlertDelivery >── ChannelPost
                  │                              │
                  │                              └──< PostApplication
                  │
             (Chapa / Telebirr / bank)

ChannelPost ──> Telegram channel
            ──> Facebook page (optional)
            ──> jobs.JobPost (optional link)
            ──> tenants.Organization (optional owner)
```

`IntegrationSettings` is a singleton (`pk=1`) holding all integration credentials and branding.

### Social layer

```
User ──< Connection >── User
User ──< Post ──< PostLike
             └──< PostComment
User ──< SavedJob >── jobs.JobPost
User ──< Notification
User ──< Message >── User   (shared with jobs.Message)
```

### Tenancy

```
Organization ──< Membership >── User
             ──< Invitation
             ──< TenantSubscription >── TenantPlan
             ──< TenantAuditLog
             ──< JobPost / ChannelPost
```

`JobPost.organization` and `ChannelPost.organization` make content private to a workspace when set. Reads should go through `tenants.services.scope()`.

### Other modules

- **Recruitment** — `Application` links a user to a `jobs.Job`.
- **Freelancer** — `Skill`, `FreelancerProfile`, `JobPosting`, `Bid`.
- **Employers** — `Employer` profile (one-to-one with user).
- **Broker network** — `Broker`, `Deal`, `Payout`, `Task`.

## 8. Templates and static assets

- Site-wide templates: `templates/` (`base.html`, plus auth/app templates).
- App templates: `<app>/templates/...`.
- Admin overrides: `admin_templates/` (filesystem loader runs before app dirs).
- Custom dashboard templates: `dashboard/templates/dashboard/`.
- Social templates: `social/templates/social/`.
- Static source: `static/`; collected output: `staticfiles/`.
- The custom dashboard and social layer load `css/tailwind.css` plus Bootstrap Icons from a CDN.

## 9. Background work

| Task | Mechanism | Command |
|---|---|---|
| Publish channel posts | Manual action or service function | Dashboard/API or Django admin |
| Alert subscribers | `billing.services.publish_post(..., alert=True)` | Called on publish |
| Expiry reminders | Management command | `renewal_reminders` |
| Daily digest | Management command | `send_digest` |
| Tender/job scraping | Management commands | `scrape_tenders`, `post_website_update` |
| Talent sync | Management command | `sync_talents` |
| Telegram bot | Long-running process | `bot/bot.py` |

Schedule the commands with cron, Task Scheduler, or a process supervisor. See [DEPLOYMENT.md](DEPLOYMENT.md).

## 10. Design conventions

- Function-based views with decorators; no DRF viewsets for existing endpoints.
- Explicit route names and namespaces (`dashboard:`, `social:`, `billing:`, `tenants:`, `jobs:`).
- Business logic lives in `billing/services.py`, `tenants/services.py`, and `billing/config.py`; views stay thin.
- Templates use utility classes and small local style blocks; there is no front-end build pipeline.
- Migrations are committed per app. New apps must be added to `INSTALLED_APPS` and given `migrations/__init__.py`.
- Secrets belong in `.env` or the admin settings row, never in tracked files.
