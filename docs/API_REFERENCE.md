# API Reference

Most existing endpoints are plain Django function views returning `JsonResponse`. They are **not** DRF viewsets. Django REST Framework is installed and configured for new work, but the endpoints below do not use it.

## 1. Conventions

- Request bodies are JSON unless stated otherwise.
- Responses are JSON objects with `success` where implemented.
- Authentication is the Django **session cookie** unless the endpoint is marked public.
- CSRF applies unless the view is marked `csrf_exempt`; for browser clients, send the `csrftoken` cookie and `X-CSRFToken` header.
- Error responses generally use `{"success": false, "error": "..."}` or `{"success": false, "message": "..."}` depending on the view. Check the specific endpoint.
- Dates are ISO 8601 strings where serialized.

### Auth summary

| Type | Meaning |
|---|---|
| Public | No login required |
| Session | Requires an authenticated session |
| Staff | Requires `is_staff` (or superuser) |
| Employer | Requires a `ClientProfile` or active workspace membership |

## 2. Authentication and registration

### `POST /api/login/`

Public, `csrf_exempt`. Logs in with email + password.

```json
{ "email": "user@example.com", "password": "secret" }
```

Success:

```json
{
  "success": true,
  "message": "Welcome back, Jane Doe!",
  "user": {
    "id": 12,
    "email": "user@example.com",
    "first_name": "Jane",
    "last_name": "Doe",
    "role": "job_seeker",
    "profile_image": null
  }
}
```

Errors: `400` missing fields/invalid JSON, `401` invalid credentials, `405` non-POST.

### `GET /api/current-user/`

Public but returns 401 JSON when anonymous.

```json
{ "authenticated": false, "user": null }
```

or

```json
{ "authenticated": true, "user": { "...": "..." } }
```

### `POST /api/logout/`

`csrf_exempt`; logs out and returns `{"success": true, "message": "Logged out"}`.

### `POST /api/register/seeker/`

Public, JSON.

| Field | Required |
|---|---|
| `first_name`, `last_name`, `email`, `password` | Yes |
| `title`, `phone`, `country`, `city`, `rate`, `experience`, `skills`, `bio` | Optional |

`skills` may be a list or a comma-separated string. Returns `success` and the created user/profile identifiers. Creates the user with the email as username.

### `POST /api/register/employer/`

Public, JSON.

| Field | Required |
|---|---|
| `company`, `first_name`, `last_name`, `email`, `password`, `phone` | Yes |
| `address`, `website` | Optional |

Creates a `ClientProfile` and adds the user to the `Client` group.

### `POST /billing/auth/telegram/`

Public, `csrf_exempt`, JSON. See [BILLING_AND_TELEGRAM.md](BILLING_AND_TELEGRAM.md).

```json
{ "initData": "<Telegram WebApp initData>" }
```

Returns `success`, `created`, and `user` with `role` (`employer`, `job_seeker`, `new`). Invalid signatures return `403`.

## 3. Jobs

### `GET /api/jobs/`

Public. Returns approved `jobs.Job` rows, newest first.

```json
{
  "success": true,
  "count": 2,
  "jobs": [
    {
      "id": 1,
      "title": "Django Developer",
      "company": "Acme",
      "location": "Addis Ababa",
      "job_type": "Full-time",
      "salary": "50000.00",
      "description": "...",
      "category": "IT",
      "posted_date": "2026-11-01T10:00:00+00:00",
      "is_approved": true,
      "experience_required": 2
    }
  ]
}
```

### `GET /api/jobs/<job_id>/`

Public. Returns one job or `404`.

Adds `employer_email` when a client profile exists.

### `GET /api/dashboard-metrics/`

Public (no explicit guard). Returns user/job/talent counts, recent users, and a 7-day job chart.

### `GET /api/categories/`

Public. Returns `{"success": true, "categories": [{"id": 1, "name": "..."}]}` using `JobCategory` when available, otherwise distinct talent categories.

## 4. Job seekers

### `GET /api/job-seekers/`

Session required (`@login_required`). Returns all profiles for the staff dashboard:

```json
{
  "success": true,
  "count": 1,
  "seekers": [
    {
      "id": 3,
      "first_name": "Jane",
      "last_name": "Doe",
      "full_name": "Jane Doe",
      "email": "jane@example.com",
      "username": "jane@example.com",
      "title": "Developer",
      "phone": "+251...",
      "country": "Ethiopia",
      "city": "Addis Ababa",
      "hourly_rate": 500.0,
      "experience": 3,
      "skills": ["Python"],
      "is_verified": false,
      "email_verified": false,
      "is_active": true,
      "date_joined": "2026-01-01",
      "date_joined_timesince": "10 months",
      "avatar_initial": "J"
    }
  ]
}
```

### `POST /api/admin/add-job-seeker/`

`csrf_exempt`, POST. Admin-style creation without OTP.

Required: `first_name`, `last_name`, `email`, `password`, `role`.
Optional: `phone`, `bio`.

Creates a user in the `JobSeeker` group and a verified `JobSeekerProfile`.

### `POST /api/admin/verify-job-seeker/`

`csrf_exempt`, POST. Sets verification explicitly.

```json
{ "user_id": 12, "verified": true }
```

### `POST /api/job-seekers/<seeker_id>/toggle-verify/`

`csrf_exempt`, POST. Toggles `JobSeekerProfile.is_verified`.

```json
{ "success": true, "message": "User Jane Doe is now verified.", "verified": true }
```

> These verification endpoints have **no staff guard** in the current code. Restrict them at the web server or add `@user_passes_test(lambda u: u.is_staff)` before exposing the API publicly.

## 5. Talents

### `GET /api/talents/`

Public. Returns talents ordered by rating/reviews with display category, price, rating, skills, image, availability, and portfolio.

### `GET /api/talent/<talent_id>/`

Session required (`@login_required`). Returns one talent with contact-adjacent fields. `404` when missing.

### `PUT/POST/PATCH /api/talent/<talent_id>/update/`

Session required **and** `is_staff`. Accepts JSON or multipart form data (`photo` file supported). Updates allowed talent fields. Returns `403` for non-staff.

### `POST /api/talents/upload-photo/`, `/remove-photo/`, `/fix-images/`

Staff/session endpoints used by the talent editor. See `jobs/views.py` for the exact field expectations.

## 6. Social

The social layer is HTML, not JSON, except for the like endpoint's optional AJAX response.

### `GET /social/like/<post_id>/`

Session required. Toggles a like. With header `X-Requested-With: XMLHttpRequest`:

```json
{ "likes": 4 }
```

Otherwise redirects to `/social/`.

Other social routes are form posts/redirects. See [SOCIAL_FEATURES.md](SOCIAL_FEATURES.md).

## 7. Billing, subscriptions, and employer tools

All employer endpoints live under `/billing/api/employer/...` because `billing/urls.py` is included at `/billing/`.

### `POST /billing/api/employer/post-job/`

Session required. Employer only. Requires an active subscription (`402` otherwise).

JSON body:

| Field | Required | Notes |
|---|---|---|
| `title` | Yes | |
| `description` | Yes | |
| `location` | No | Defaults to profile location |
| `budget` | No | Decimal string |
| `category_tag` | No | Used for matched alerts |
| `deadline` | No | `YYYY-MM-DD`; defaults to +30 days |
| `source_url` | No | |
| `organization_slug` | No | Required if the user belongs to multiple workspaces |

Success:

```json
{
  "success": true,
  "post_id": 10,
  "message_id": 1234,
  "job_post_id": 7,
  "organization": "acme",
  "organization_created": false,
  "quota": { "...": "..." },
  "message": "Posted \"...\" to the channel."
}
```

Errors:

| Status | Meaning |
|---|---|
| `401` | Not signed in |
| `403` | Not an employer or no workspace permission |
| `402` | No active subscription, or quota blocked (`code: quota_blocked`) |
| `409` | Multiple workspaces; send `organization_slug` |
| `502` | Telegram publish failed |

### `GET /billing/api/employer/my-posts/`

Session required. Employer only. Optional `organization_slug`. Returns up to 50 posts with status, organization, publisher, publish time, Telegram message ID, applicant count, and publish error.

### `GET /billing/api/employer/applications/`

Session required. Employer only. Optional `organization_slug`, `post_id`, `status`. Returns up to 100 applicants with name, title, skills, location, rate, verification, status, note, and creation time.

### `POST /billing/api/employer/applications/<application_id>/`

Session required. Employer only. JSON:

```json
{ "status": "shortlisted", "admin_note": "Great portfolio" }
```

Allowed statuses: `submitted`, `reviewing`, `shortlisted`, `rejected`.

Sends a Telegram DM to the applicant when a chat ID resolves.

### `GET /billing/api/alerts/preferences/`

Session required. Returns `subscribed: false` when there is no active subscription, otherwise the alert mode, digest hour, mute flag, expiry, and available modes.

### `POST /billing/api/alerts/preferences/set/`

Session required. JSON:

```json
{ "mode": "digest", "hour": 8, "muted": false }
```

`mode` is `immediate`, `digest`, or `matched`. `hour` must be 0–23.

### `POST /billing/chapa/webhook/`

Public, `csrf_exempt`, POST. Always returns HTTP 200. See [BILLING_AND_TELEGRAM.md](BILLING_AND_TELEGRAM.md).

### `GET /billing/analytics/`

Staff only. Returns:

```json
{
  "subscriptions": {
    "total": 0, "active": 0, "pending_review": 0, "expired": 0, "rejected": 0
  },
  "revenue_active_etb": "0",
  "posts": { "total": 0, "published": 0, "failed": 0 },
  "applications": { "total": 0, "submitted": 0, "shortlisted": 0, "rejected": 0 },
  "alerts": { "deliveries": 0, "successful": 0 }
}
```

## 8. Tenants

Base: `/tenants/api/`.

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/tenants/api/plans/` | Active plans |
| GET | `/tenants/api/organizations/` | Organizations visible to the user |
| POST | `/tenants/api/organizations/create/` | Create an organization |
| GET | `/tenants/api/organizations/<slug>/` | Organization detail |
| GET | `/tenants/api/organizations/<slug>/dashboard/` | Workspace dashboard data |
| GET | `/tenants/api/organizations/<slug>/quota/` | Plan/quota usage |
| GET | `/tenants/api/organizations/<slug>/members/` | Members |
| POST | `/tenants/api/organizations/<slug>/members/invite/` | Invite a member |
| POST | `/tenants/api/organizations/<slug>/members/<user_id>/role/` | Change role |
| POST | `/tenants/api/organizations/<slug>/members/<user_id>/remove/` | Remove member |
| GET | `/tenants/api/invitations/` | My pending invitations |
| POST | `/tenants/api/invitations/<uuid>/accept/` | Accept invitation |

Most require a session and membership; write operations also check roles. The HTML workspace pages live under `/tenants/workspaces/...`.

## 9. Telegram and mini app

| Endpoint | Method | Purpose |
|---|---|---|
| `/miniapp/` | GET | Mini app HTML shell |
| `/mini-app/` (jobs) | GET | Alias shell |
| `/billing/auth/telegram/` | POST | `initData` login |
| `/telegram-webhook/` | POST | Telegram updates |
| `/tg/wh/` | POST | Telegram updates alias |

The webhook always returns `{"ok": true}` and logs errors, so Telegram does not retry indefinitely. It requires the bot application to be importable and Django configured.

## 10. Error handling and testing

Example with `curl` (session cookie required for protected endpoints):

```bash
curl -i -c cookies.txt -b cookies.txt \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: $CSRF" \
  -d '{"title":"Django Developer","description":"Build APIs"}' \
  http://127.0.0.1:8000/billing/api/employer/post-job/
```

Recommended checks:

1. Anonymous access to protected endpoints returns `401` or a login redirect (HTML views).
2. Non-employer access to employer endpoints returns `403`.
3. Missing subscription returns `402`.
4. Invalid JSON returns `400`, not a traceback.
5. Chapa webhook always returns HTTP 200.

## 11. Known API gaps

- No DRF serializers or schema (OpenAPI) yet.
- Some admin-sensitive endpoints (`toggle-verify`, `add-job-seeker`, `verify-job-seeker`) are `csrf_exempt` and lack staff guards.
- `api_job_seekers` returns **all** profiles to any logged-in user; restrict to staff.
- `dashboard_metrics` and several read endpoints have no explicit permission check.
- No rate limiting.
- Error key naming is inconsistent (`error` vs `message`).
- No pagination on most list endpoints (some cap at 50/100 rows).

Before exposing these APIs to a public client, add guards, rate limits, and a consistent response envelope.
