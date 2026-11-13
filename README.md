# Ethiogen Job Seeker Hub

A Django 6 job portal and professional network for the Ethiopian market. It combines job discovery, employer workspaces, subscriptions, a Telegram distribution bot, and a custom staff admin console.

| | |
|---|---|
| **Framework** | Django 6.0.x (Python 3.12+) |
| **Database** | SQLite by default, PostgreSQL supported |
| **Front-end** | Django templates, Tailwind-style utility CSS, Bootstrap Icons |
| **Bots / integrations** | Telegram Bot API, Chapa, Telebirr, bank transfer, Facebook Pages |
| **Entry points** | Public site `/`, custom admin `/admin/`, raw Django admin `/django-admin/`, social network `/social/` |

---

## Quick start

```powershell
# From the project root
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

Copy-Item .env.example .env      # then edit values
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 127.0.0.1:8000
```

Open <http://127.0.0.1:8000/> for the public site and <http://127.0.0.1:8000/admin/> for the staff dashboard.

On Linux/macOS use `source venv/bin/activate` and `cp .env.example .env`.

> **Important:** `DEBUG` defaults to **off**. For local development add `DJANGO_DEBUG=1` to `.env`, otherwise Django will return 400/500 pages without tracebacks.

---

## What is in the project

- **Public job portal** — home page, job listings, job seeker profiles, employer and client dashboards, checkout, reviews, OTP verification, Amharic/English language switch.
- **Custom admin console** (`/admin/`) — KPI home, subscriptions, channel posts, users, organizations, job seekers, applications, configuration, and an "All Models" index for the whole Django admin registry.
- **Integration settings** — a singleton settings row editable from the dashboard: Telegram bot/channel/group, mini app, Chapa, Telebirr, bank transfer, subscription price/duration, branding/logo, Facebook page.
- **Subscription billing** — manual receipt review and Chapa checkout, activation, expiry, and reminder workflows.
- **Telegram distribution** — publish jobs/tenders to a channel, inline Apply/Subscribe buttons, admin bot commands, alert delivery tracking, daily digest.
- **LinkedIn-style social layer** (`/social/`) — professional feed with likes and comments, connections, saved jobs, notifications, and direct messages.
- **Employer workspaces** — multi-tenant organizations, memberships, invitations, plans, quotas, audit log, and an operator console.
- **Recruitment and freelancing** — job postings/applications and a separate freelancer bidding module.
- **Explainable job matching** — rules-based, transparent seeker/job and employer/candidate scores with reasons, gaps, and JSON endpoints; no external AI provider required.
- **Broker network** — brokers, deals, payouts, and tasks (scaffolding/legacy module).
- **Management commands** — seeding, verification resets, scraping, Telegram verification, bot simulation, digests, reminders, and PostgreSQL migration tooling.

---

## Documentation

Full documentation lives in [`docs/`](docs/README.md).

| Document | What it covers |
|---|---|
| [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md) | Prerequisites, installation, environment, first run, first login |
| [docs/USER_GUIDE.md](docs/USER_GUIDE.md) | Step-by-step usage for seekers, employers, subscribers, and staff |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Project layout, request lifecycle, settings, URL map, data model overview |
| [docs/APPS.md](docs/APPS.md) | Every Django app, its models, views, and responsibilities |
| [docs/ADMIN_DASHBOARD.md](docs/ADMIN_DASHBOARD.md) | Custom admin console, pages, actions, theme, raw Django admin |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | Every configuration section and environment variable |
| [docs/SOCIAL_FEATURES.md](docs/SOCIAL_FEATURES.md) | Feed, connections, saved jobs, notifications, messaging |
| [docs/AI_MATCHING.md](docs/AI_MATCHING.md) | Explainable matching, weights, permissions, JSON endpoints |
| [docs/BILLING_AND_TELEGRAM.md](docs/BILLING_AND_TELEGRAM.md) | Subscription flow, Chapa, manual payments, bot commands, alerts |
| [docs/API_REFERENCE.md](docs/API_REFERENCE.md) | JSON endpoints, Telegram auth, employer API, analytics |
| [docs/MANAGEMENT_COMMANDS.md](docs/MANAGEMENT_COMMANDS.md) | All custom `manage.py` commands with usage |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Production checklist, static/media, cPanel, PostgreSQL, security |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Common errors and fixes |
| [docs/POSTGRES.md](docs/POSTGRES.md) | Existing PostgreSQL migration guide |

---

## URL cheat sheet

| URL | Purpose | Access |
|---|---|---|
| `/` | Public home page | Public |
| `/jobs/` | Job listings | Public |
| `/accounts/login/` | Login | Public |
| `/accounts/register/` | Registration | Public |
| `/admin/` | Custom staff dashboard | `is_staff` |
| `/admin/settings/` | Integration configuration | `is_staff` |
| `/admin/admin-models/` | All registered Django models | `is_staff` |
| `/django-admin/` | Raw Django admin | `is_staff` |
| `/social/` | Professional feed | Authenticated |
| `/social/connections/` | Network and requests | Authenticated |
| `/social/saved-jobs/` | Saved jobs | Authenticated |
| `/social/notifications/` | Notifications | Authenticated |
| `/social/inbox/` | Direct messages | Authenticated |
| `/matches/` | Recommended jobs | Signed-in seeker with profile |
| `/matches/candidates/` | Employer candidate matching | Job owner or staff |
| `/matches/jobs/<id>/candidates/` | Candidate ranking for one job | Job owner or staff |
| `/matches/api/jobs/` | Matching JSON API | Signed-in seeker with profile |
| `/matches/api/jobs/<id>/candidates/` | Candidate JSON API | Job owner or staff |
| `/billing/analytics/` | Staff analytics JSON | `is_staff` |
| `/billing/chapa/webhook/` | Chapa webhook (POST) | Public, CSRF-exempt |
| `/telegram-webhook/` | Telegram webhook (POST) | Public |
| `/miniapp/` | Telegram mini app | Public |
| `/tenants/workspaces/` | Employer workspaces | Authenticated |
| `/tenants/console/` | Operator console | Superuser |
| `/recruitment/` | Recruitment job board | Authenticated |
| `/freelancingjobs/` | Freelance job board | Public |

---

## Repository layout (top level)

```
manage.py                  Django entry point
job_portal/                Settings, URLs, WSGI/ASGI
accounts/                  Custom user + roles + auth pages
jobs/                      Core job portal, profiles, talents, API, bot models
billing/                   Subscriptions, channel posts, integrations, payments
dashboard/                 Custom staff admin console
social/                    LinkedIn-style feed, connections, messages
ai_engine/                 Explainable job matching (rules-based, no models)
tenants/                   Multi-tenant employer workspaces
recruitment/               Simple recruitment postings/applications
freelancer/                Freelance job posting and bidding
employers/                 Employer profile module
borker_network/            Broker/deal/payout/task module
users/                     Thin user app (no models)
bot/                       Telegram bot process
templates/                 Site-wide templates
static/                    Source static assets
staticfiles/               collectstatic output
media/                     User uploads
docs/                      Documentation
```

---

## Health check

```bash
python manage.py check
python manage.py showmigrations
```

The project is expected to report **0 issues** from `check`. If you change models, run:

```bash
python manage.py makemigrations
python manage.py migrate
```

---

## License / ownership

Internal project for Ethiogen. Replace this section with the applicable license before distributing outside the organization.
