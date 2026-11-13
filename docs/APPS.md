# Application Reference

The project is split into focused Django apps. This document lists each app, its models, its main views/routes, and operational notes.

## Summary table

| App | Purpose | Has models | Has migrations |
|---|---|---|---|
| `accounts` | Custom user, roles, login/registration | Yes | Yes |
| `jobs` | Core portal, profiles, talents, JSON API, bot models | Yes | Yes |
| `billing` | Subscriptions, channel posts, payments, integrations | Yes | Yes |
| `dashboard` | Custom staff admin console | No | No |
| `social` | Feed, connections, saved jobs, notifications, messages | Yes | Yes |
| `tenants` | Multi-tenant organizations and workspaces | Yes | Yes |
| `recruitment` | Simple recruitment postings/applications | Yes | Yes |
| `freelancer` | Freelance jobs and bids | Yes | Yes |
| `employers` | Employer profile | Yes | Yes |
| `borker_network` | Broker/deal/payout/task module | Yes | Yes |
| `users` | Thin placeholder app | No | No |

---

## `accounts`

**Purpose:** authentication, registration, roles, and role-aware redirects.

**Models**

| Model | Key fields | Notes |
|---|---|---|
| `Role` | `name` (`super_admin`, `admin`, `employer`, `job_seeker`), `description`, `permissions` (M2M to `auth.Permission`) | Roles are data, not Django groups |
| `User` | `AbstractUser` + `role` FK, `is_verified`, `is_suspended`, `suspension_reason`, `last_login_ip` | `AUTH_USER_MODEL = 'accounts.User'` |

**Views and routes**

| Route | View | Behaviour |
|---|---|---|
| `/register/` | `register` | Creates a user, redirects to login, preserves `next` |
| `/login/` | `login_view` | Authenticates; honours safe `next`; otherwise role-based redirect |
| `/logout/` | `logout_view` | Logs out; optional safe `next`; defaults to home |

**Login redirect priority**

1. `next` parameter, if it starts with `/`.
2. Staff → `jobs:construction_dashboard`.
3. Verified job seeker → `jobs:job_seeker_dashboard`; unverified → `jobs:verify_otp`.
4. Client profile → `jobs:employer_dashboard`.
5. No profile → `jobs:client_profile`.

**Templates:** `accounts/templates/accounts/{login,register,change_password}.html`.

**Notes**

- `accounts/templatetags/form_tags.py` provides form-rendering helpers.
- Password change is exposed through `jobs.urls` at `/change-password/`, using `registration/change_password.html`.

---

## `jobs`

**Purpose:** the core public portal, profiles, talents, JSON API, Telegram webhook, and the data models used by the bot.

**Models**

### Catalogues

| Model | Purpose |
|---|---|
| `Category` / `SubCategory` | Job categories with Amharic names |
| `JobCategory` | Legacy category model |
| `Profession` | Skills/professions used by profiles and jobs |
| `ProfessionalRate` | Published daily/weekly rate card |

### People and profiles

| Model | Purpose |
|---|---|
| `ClientProfile` | Employer/client profile (company, location, verification) |
| `JobSeekerProfile` | Professional profile: title, profession, bio, photo, rates, skills, certifications, CV, verification, OTP fields |
| `TelegramProfile` | Links a user to a Telegram `chat_id` |
| `UserPreference` | Language and currency |
| `Talent` | Curated/marketed talent record (price, rating, tiers, portfolio) |
| `WorkerVerification` | One-to-one verification status |
| `WorkerAvailability` | One-to-one availability window |
| `WorkerPortfolio` | Portfolio items |

### Work and transactions

| Model | Purpose |
|---|---|
| `Job` | Client job request with approval, assignment, completion |
| `Booking` | Scheduled engagement between client and provider |
| `JobPost` | Job posting used by the bot/API, optionally owned by an organization |
| `JobApplication` | Application to a `JobPost` |
| `Review` | Review tied to a completed `Job` |
| `WorkerRating` | Rating for a job seeker |
| `FavoriteWorker` | Client's saved workers |
| `TalentAccess` | Paid contact access for a talent |
| `HireRequest` / `PostNeedRequest` | Inbound hire/need requests |
| `Message` | Direct message between users |
| `ScrapedContent` | Deduplication log for scraped content |

**Main routes** (`jobs/urls.py`)

| Route | View |
|---|---|
| `/` | `home` |
| `/language/<lang>/` | `change_language` |
| `/construction_workforce/`, `/business_consultancy/` | Static marketing pages |
| `/register/job-seeker/` | `job_seeker_register` |
| `/verify-otp/`, `/resend-otp/` | OTP flow |
| `/dashboard/` | `job_seeker_dashboard` |
| `/profile/create/`, `/profile/<pk>/` | Profile create/view |
| `/browse/` | `browse_job_seekers` |
| `/jobs/`, `/jobs/add/`, `/jobs/<id>/` | Job list/add/details |
| `/client/profile/`, `/client/dashboard/`, `/client/jobs/create/` | Client pages |
| `/employer-dashboard/`, `/checkout/`, `/pay-for-talent/<id>/` | Employer and payment |
| `/jobs/<job_id>/review/<provider_id>/` | Create review |
| `/hire-request/`, `/post-need/`, `/update-session/` | AJAX/session endpoints |
| `/admin/dashboard/` | Legacy staff dashboard |
| `/construction/` | Construction dashboard |
| `/api/...` | JSON API (see [API_REFERENCE.md](API_REFERENCE.md)) |
| `/telegram-webhook/`, `/mini-app/` | Bot and mini app |
| `/change-password/`, `/logout/` | Auth utilities |

**Notes**

- `jobs/apps.py` imports `jobs.signals` in `ready()`, so signals load at startup.
- `jobs/telegram_utils.py` contains Telegram helpers used by the webhook and commands.
- `jobs/utils/file_watcher.py` backs the optional `start_file_watcher` command.
- `jobs/admin_missing.py` registers additional admin classes; `jobs/admin.py` holds the main registrations.

---

## `billing`

**Purpose:** Telegram channel distribution, subscription billing, payment providers, integration settings, and employer APIs.

**Models**

| Model | Purpose |
|---|---|
| `IntegrationSettings` | Singleton (`pk=1`) for Telegram, Chapa, Telebirr, bank, subscription defaults, branding, Facebook |
| `ChannelPost` | A message published to Telegram/Facebook, with inline buttons and delivery bookkeeping |
| `Subscription` | User subscription with status, payment method, Chapa reference, receipt, review, expiry, alert preferences |
| `AlertDelivery` | One row per (subscription, post) alert; prevents duplicates and records failures |
| `PostApplication` | Application submitted from a channel post's Apply button |

**Services** (`billing/services.py`)

| Function | Purpose |
|---|---|
| `send_to_channel`, `send_to_user` | Telegram sends |
| `resolve_chat_id(user)` | Map a user to a Telegram chat |
| `publish_post(post, alert=True)` | Publish to Telegram, optionally notify subscribers |
| `init_chapa_checkout(subscription)` | Create a Chapa checkout |
| `handle_chapa_webhook(data)` | Process a Chapa payment notification |
| `activate_subscription(...)` / `reject_subscription(...)` | Review workflow and notifications |
| `has_active_subscription(user)` | Access check |
| `record_application(post, user)` | Create/return a `PostApplication` |
| `notify_application_status(application)` | Notify the applicant |

**Other modules**

| File | Purpose |
|---|---|
| `billing/config.py` | Cached configuration accessors and diagnostics |
| `billing/emails.py` | Email helpers |
| `billing/facebook.py` | Facebook Page publishing |
| `billing/alerts.py` | Subscriber alert/digest logic |
| `billing/telegram_auth.py` | Mini app `initData` HMAC verification and user upsert |
| `billing/employer_api.py` | JSON APIs for employers (post job, my posts, applications, alert prefs) |
| `billing/views.py` | Chapa webhook, analytics, Telegram login |

**Routes** (`billing/urls.py`)

| Route | View |
|---|---|
| `/billing/chapa/webhook/` | `chapa_webhook` (POST, CSRF-exempt) |
| `/billing/analytics/` | `analytics_dashboard` (staff JSON) |
| `/billing/auth/telegram/` | `telegram_login` (POST JSON) |
| `/billing/api/alerts/preferences/` | `get_alert_preferences` |
| `/billing/api/alerts/preferences/set/` | `set_alert_preferences` |
| `/billing/api/employer/post-job/` | `employer_post_job` |
| `/billing/api/employer/my-posts/` | `employer_my_posts` |
| `/billing/api/employer/applications/` | `employer_applications` |
| `/billing/api/employer/applications/<id>/` | `employer_update_application` |

**Management commands:** `renewal_reminders`, `send_digest`, `simulate_bot`, `verify_telegram`.

See [BILLING_AND_TELEGRAM.md](BILLING_AND_TELEGRAM.md) for flows.

---

## `dashboard`

**Purpose:** replace Django's default admin landing page with a purpose-built staff console at `/admin/`.

**Models:** none.

**Views/routes**

| Route | View | Purpose |
|---|---|---|
| `/admin/` | `home` | KPI overview and recent activity |
| `/admin/subscriptions/` | `subscriptions` | List/filter/paginate subscriptions |
| `/admin/subscriptions/<pk>/<action>/` | `subscription_action` | Approve or reject (POST) |
| `/admin/posts/` | `posts` | List/filter/paginate channel posts |
| `/admin/posts/<pk>/publish/` | `post_publish` | Publish to Telegram (POST) |
| `/admin/users/` | `users` | User list and search |
| `/admin/organizations/` | `organizations` | Organization list and filters |
| `/admin/job-seekers/` | `job_seekers` | Job seeker list and search |
| `/admin/applications/` | `applications` | Post applications and status filter |
| `/admin/settings/` | `settings_view` | Integration configuration UI |
| `/admin/settings/save/` | `settings_save` | Save one section (POST) |
| `/admin/admin-models/` | `admin_models` | Every registered admin model, grouped by app |

All views require `is_staff`. See [ADMIN_DASHBOARD.md](ADMIN_DASHBOARD.md).

---

## `social`

**Purpose:** a LinkedIn-style professional layer.

**Models**

| Model | Purpose |
|---|---|
| `Connection` | Directed connection request with `pending`/`accepted`/`rejected` |
| `Post` | Feed post (text, optional image) |
| `PostLike` | Unique like per (post, user) |
| `PostComment` | Comment on a post |
| `SavedJob` | Unique saved job per (user, job) |
| `Notification` | In-app notification (connection, like, comment, message, job, system) |

**Routes** (`/social/`)

| Route | View |
|---|---|
| `/social/` | `feed` (GET + POST create) |
| `/social/like/<post_id>/` | `like_post` (toggles) |
| `/social/comment/<post_id>/` | `comment_post` |
| `/social/connections/` | `connections` |
| `/social/connect/<user_id>/` | `connect` |
| `/social/connections/<pk>/<action>/` | `connection_action` (`accept`/`reject`) |
| `/social/saved-jobs/` | `saved_jobs` |
| `/social/save-job/<job_id>/` | `save_job` |
| `/social/unsave-job/<job_id>/` | `unsave_job` |
| `/social/notifications/` | `notifications` (marks all read) |
| `/social/inbox/` | `inbox` (list + send) |

See [SOCIAL_FEATURES.md](SOCIAL_FEATURES.md).

---

## `tenants`

**Purpose:** multi-tenant employer workspaces and a platform operator console.

**Models**

| Model | Purpose |
|---|---|
| `Organization` | Tenant/company with status, type, verification, branding, Telegram chat |
| `Membership` | User ↔ organization with role (`owner`, `admin`, `recruiter`, `viewer`, etc.) |
| `Invitation` | Email invitation with UUID token and expiry |
| `TenantPlan` | Plan limits: price, cycle, job post limit, seat limit, featured posts, own channel, export |
| `TenantSubscription` | Organization subscription and usage counters |
| `TenantAuditLog` | Audit trail of workspace actions |

**Pages**

| Route | Purpose |
|---|---|
| `/tenants/workspaces/` | List workspaces |
| `/tenants/workspaces/new/` | Create workspace |
| `/tenants/workspaces/<slug>/` | Workspace detail |
| `/tenants/workspaces/<slug>/members/` | Members and invitations |
| `/tenants/workspaces/<slug>/billing/` | Plan/billing |
| `/tenants/workspaces/<slug>/jobs/` | Organization jobs |
| `/tenants/invitations/<uuid>/` | Accept invitation |
| `/tenants/console/` | Operator dashboard (superuser) |
| `/tenants/console/organizations/` | Organization management |
| `/tenants/console/plans/` | Plan management |

**JSON API:** `/tenants/api/plans/`, `/tenants/api/organizations/...`, `/tenants/api/invitations/...`.

**Notes**

- `tenants/services.py` provides scoping helpers (use `scope()` for organization-private rows).
- `tenants/provisioning.py` creates default organization resources.
- `tenants/ecosystem.py` adds an `/admin/ecosystem/` page to the **raw** Django admin.
- `tenants/context_processors.py` exposes platform admin counts.

---

## `recruitment`

**Purpose:** a simple recruitment board separate from the main job portal.

**Model:** `Application` — applicant user, `jobs.Job`, cover letter, resume, applied timestamp.

**Routes**

| Route | View |
|---|---|
| `/recruitment/` | `job_postings` |
| `/recruitment/create/` | `create_job_posting` |
| `/recruitment/<id>/apply/` | `apply_for_job` |

---

## `freelancer`

**Purpose:** freelance job posting and bidding.

**Models**

| Model | Purpose |
|---|---|
| `Skill` | Unique skill name |
| `FreelancerProfile` | One-to-one profile with skills, bio, portfolio |
| `JobPosting` | Freelance job with budget and deadline |
| `Bid` | Unique bid per (freelancer, job) |

**Routes**

| Route | View |
|---|---|
| `/profile/` | `freelancer_profile` |
| `/create_job/` | `create_job_posting` |
| `/freelancingjobs/` | `list_freelancing_job` |
| `/jobs/<id>/` | `job_detail` |
| `/jobs/<id>/bid/` | `place_bid` |

---

## `employers`

**Purpose:** employer profile and an employer-facing page. It also includes `jobs.urls`.

**Model:** `Employer` — one-to-one with user, company name, website, description.

**Routes:** `employers/urls.py` defines the employer page and includes `jobs.urls` under the `jobs` namespace. Because the root `job_portal/urls.py` also includes `jobs.urls` without a namespace, both URL styles resolve.

---

## `borker_network`

**Purpose:** a broker network module (legacy/scaffolding).

**Models**

| Model | Purpose |
|---|---|
| `Broker` | One-to-one with user, phone, address, network level, balance |
| `Deal` | Client deal, amount, commission, status |
| `Payout` | Broker payout and status |
| `Task` | Broker task with deadline and completion |

The app name is intentionally `borker_network` (misspelling preserved to avoid migration churn). Do not rename it without a data migration plan.

---

## `users`

**Purpose:** placeholder app. It has `admin.py`, `apps.py`, `views.py`, and tests, but **no models and no migrations**. The actual user model lives in `accounts`.

---

## `bot`

**Purpose:** a standalone Telegram bot process (`python-telegram-bot` v22).

Main file: `bot/bot.py`.

**Commands registered**

| Command | Purpose |
|---|---|
| `/start` | Onboarding, referral handling, subscription gate |
| `/invite` | Referral link |
| `/test` | Connectivity test |
| `/scrape` | Run the job scraper (admin only) |
| `/tenders` | Run the tender scraper (admin only) |
| `/approve` | Approve a subscription (admin only) |
| `/reject` | Reject a subscription (admin only) |
| `/stats` | Platform stats (admin only) |

The bot also handles inline callbacks for browsing/filtering talents, job posting, applications, hiring, ratings, favorites, nearby search, language/currency settings, and the subscription flow.

**Supporting files**

| File | Purpose |
|---|---|
| `bot/telegram_bridge.py` | Bridge helpers |
| `bot/generate_secret.py` | Webhook secret generation |
| `bot/running_man.py` | Standalone animation script, not part of the app |
| `start_bot.sh` | Production start script (PID/log handling) |

See [BILLING_AND_TELEGRAM.md](BILLING_AND_TELEGRAM.md).

---

## `tools`

Operational scripts, not Django apps:

| File | Purpose |
|---|---|
| `build_logo.py` | Generate branding assets |
| `check_admin_templates.py` | Verify admin template overrides resolve |
| `deploy_check.py` | Pre-deployment checks |
| `migrate_to_postgres.py` | SQLite → PostgreSQL data migration |
| `pg_bootstrap.py` | PostgreSQL role/database bootstrap |
| `rebrand_logos.py` | Rewrite logos across the project |

---

## `job_portal`

The project package itself:

| File | Purpose |
|---|---|
| `settings.py` | Configuration |
| `urls.py` | Root URL map |
| `wsgi.py` / `asgi.py` | Server entry points |
| `__init__.py` | Installs PyMySQL as `MySQLdb` |
