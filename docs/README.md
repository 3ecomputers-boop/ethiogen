# Ethiogen Documentation

This directory is the reference manual for the Ethiogen Job Seeker Hub. Each document is self-contained; start with **Getting Started** if you are new to the project.

## Reading order

1. [Getting Started](GETTING_STARTED.md) — install, configure, run, log in.
2. [User Guide](USER_GUIDE.md) — how seekers, employers, subscribers, and staff use the site.
3. [Architecture](ARCHITECTURE.md) — how the project is put together.
4. [Apps](APPS.md) — what each Django app does.
5. [Admin Dashboard](ADMIN_DASHBOARD.md) — the custom staff console.
6. [Configuration](CONFIGURATION.md) — every setting and environment variable.
7. [Social Features](SOCIAL_FEATURES.md) — the LinkedIn-style layer.
8. [Billing and Telegram](BILLING_AND_TELEGRAM.md) — subscriptions, payments, bot.
9. [API Reference](API_REFERENCE.md) — JSON endpoints.
10. [Management Commands](MANAGEMENT_COMMANDS.md) — operational scripts.
11. [Deployment](DEPLOYMENT.md) — production checklist.
12. [Troubleshooting](TROUBLESHOOTING.md) — known errors and fixes.
13. [PostgreSQL Migration](POSTGRES.md) — existing guide for moving off SQLite.

## Conventions used in this manual

- Commands assume the project root (the folder containing `manage.py`).
- Windows examples use `.\venv\Scripts\python.exe`; POSIX examples use `venv/bin/python`.
- `python manage.py …` is used in prose for brevity.
- Routes are written without the scheme/host, e.g. `/admin/settings/`.
- "Staff" means `user.is_staff`; "superuser" means `user.is_superuser`.
- "Admin console" means the custom dashboard at `/admin/`; "Django admin" means the raw admin at `/django-admin/`.

## Documentation status

| Area | Documented | Notes |
|---|---|---|
| Installation and environment | Yes | `.env.example` is the canonical template |
| End-user workflows | Yes | Covers seekers, employers, subscribers, staff |
| Custom admin console | Yes | Includes every page and action |
| Integration settings | Yes | Includes fallback/resolution order |
| Social layer | Yes | Models, routes, flows, limitations |
| Billing / Telegram | Yes | Manual and Chapa flows, bot commands |
| JSON APIs | Yes | Endpoint tables and auth rules |
| Management commands | Yes | All custom commands |
| Deployment | Yes | cPanel/WSGI, static/media, PostgreSQL |
| Automated tests | Partial | Test coverage is still being expanded |
