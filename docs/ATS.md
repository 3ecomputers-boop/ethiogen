# Applicant Tracking System (ATS)

The `recruitment` app now provides a complete applicant pipeline for portal job
applications. It builds on the existing `recruitment.Application` model instead
of creating another application table.

## Statuses

| Status | Meaning |
|---|---|
| `submitted` | Application received |
| `screening` | Recruiter is reviewing the application |
| `shortlisted` | Candidate passed initial review |
| `interview` | Candidate is in the interview process |
| `offer` | Offer is being prepared or sent |
| `hired` | Candidate accepted and was hired |
| `rejected` | Application was declined |
| `withdrawn` | Candidate withdrew |

Employers can move an application to any valid status. Every change is recorded
in the timeline.

## Routes

| Route | Access | Purpose |
|---|---|---|
| `/recruitment/` | Signed-in user | Open, approved jobs |
| `/recruitment/<job_id>/apply/` | Signed-in user | Submit an application |
| `/recruitment/my-applications/` | Signed-in user | Candidate status tracker |
| `/recruitment/create/` | Employer/staff | Submit a job for approval |
| `/recruitment/employer/` | Employer/staff | ATS dashboard with per-job counts |
| `/recruitment/employer/jobs/<job_id>/` | Job owner/staff | Pipeline grouped by stage |
| `/recruitment/employer/applications/<id>/` | Job owner/staff | Candidate detail and timeline |
| `/recruitment/employer/applications/<id>/status/` | Job owner/staff | POST stage change |
| `/recruitment/employer/applications/<id>/notes/` | Job owner/staff | POST internal note |

The employer dashboard links to `/recruitment/employer/`, and the job-seeker
dashboard links to `/recruitment/my-applications/`.

## Permissions

- Applicants see only their own applications.
- The pipeline, candidate detail, stage changes, and notes require:
  - staff access, or
  - ownership through `Job.client.user`.
- Other authenticated users receive `403`.
- Internal notes are never shown on the candidate tracker.

## Data model

### `Application`

Existing fields plus:

| Field | Purpose |
|---|---|
| `status` | Pipeline stage, default `submitted`, indexed |
| `updated_at` | Last stage/record update |

`PIPELINE_STATUSES` defines the display order used by the board.

### `ApplicationEvent`

Audit trail for an application:

| Field | Purpose |
|---|---|
| `application` | Related application |
| `actor` | User who caused the event (nullable) |
| `event_type` | `created`, `status`, or `note` |
| `from_status` / `to_status` | Stage transition |
| `note` | Internal note text |
| `created_at` | Event timestamp |

Events are created automatically by `recruitment/signals.py`:

- new application → `created` event,
- stage change → `status` event,
- ATS note → `note` event.

Stage changes made in Django admin are also recorded, with `actor` left blank.

## Workflow

1. Employer creates a job at `/recruitment/create/`; it is saved with
   `is_approved=False`.
2. Staff approve the job through the normal admin flow.
3. Job seekers apply at `/recruitment/<job_id>/apply/`.
4. The applicant sees the stage and timeline at `/recruitment/my-applications/`.
5. The employer opens `/recruitment/employer/`, selects a job, and reviews
   candidates by stage.
6. The employer changes stages and adds internal notes.
7. The applicant sees status updates in their tracker.

## Tests

```bash
python manage.py test recruitment
```

Coverage includes:

- automatic creation and status events,
- note events,
- employer/owner/staff permissions,
- stage update success and invalid status handling,
- applicant tracker visibility,
- apply flow and duplicate prevention,
- approved-job filtering,
- job creation ownership and pending-approval state.

If `.env` points at PostgreSQL and the database user cannot create test
databases, run the suite against SQLite:

```powershell
$env:DB_ENGINE='sqlite'
python manage.py test recruitment
```

## Current scope

This ATS covers `recruitment.Application`, which is the portal application
flow tied to `jobs.Job`.

Two other application records exist elsewhere:

- `billing.PostApplication` for Telegram channel posts,
- `jobs.JobApplication` for `JobPost` / bot applications.

They are intentionally not copied into new tables. A future step should unify
all three behind one canonical application model and one ATS interface. Until
then, use the existing employer API for Telegram applications
(`/billing/api/employer/applications/`).

## Next extensions

- Interview scheduling and evaluation forms.
- Candidate notifications on stage changes.
- Saved views and bulk stage changes.
- CSV export.
- Unified application model across portal, Telegram, and bot sources.
