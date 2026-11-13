# Verification Review Queue

Staff can review and approve (or reject) pending job-seeker and employer profiles from a single queue at `/admin/verifications/`.

## Routes

| Route | Access | Purpose |
|---|---|---|
| `/admin/verifications/` | Staff | Verification review queue (job seekers and clients) |
| `/admin/verifications/<seeker|client>/<id>/` | Staff | POST `decision=approve` or `decision=reject` |

The dashboard sidebar links to the queue under **People → Verification Queue**.

## Workflow

1. Open `/admin/verifications/`. Use the tabs to switch between pending job seekers and pending employers.
2. Search by username, email, title, company, or location.
3. For each profile choose **Approve** or **Reject**. Approving sets `is_verified=True` on the profile (and the linked user); rejecting sets `is_verified=False`.
4. Every decision is recorded in `VerificationEvent` with the actor, action, target, optional note, and timestamp. Events are visible in the **Recent decisions** panel and in Django admin (`VerificationEvent`, read-only).

## Data model

`VerificationEvent` stores one row per staff decision:

| Field | Purpose |
|---|---|
| `job_seeker` / `client` | Exactly one target profile (enforced by a database constraint) |
| `actor` | Staff member who made the decision |
| `action` | `approved`, `rejected`, or `reset` |
| `note` | Optional staff note |
| `created_at` | Decision timestamp |

## Tests

```bash
python manage.py test dashboard
```

Coverage includes staff-only access, approve/reject for both profile types, audit-event creation, no-op when state already matches, and the recent-decisions panel.

If `.env` points at PostgreSQL and the database user cannot create test databases, run against SQLite:

```powershell
$env:DB_ENGINE='sqlite'
python manage.py test dashboard
```

## Current scope

The queue covers `JobSeekerProfile` and `ClientProfile`. Telegram/bot verification flows and the `WorkerVerification` model are not duplicated — they continue to work as before.
