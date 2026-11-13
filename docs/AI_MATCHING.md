# AI Matching Engine

The `ai_engine` app adds **explainable job matching** to the existing portal. It
scores a `jobs.JobSeekerProfile` against a `jobs.Job` and explains the result in
plain language. The current implementation is rules-based, deterministic, and
does not send profile data to an external AI provider.

This is deliberately a first slice. It gives the product useful matching today
while keeping a clean service boundary for a future LLM or embedding provider.

## Routes

| Route | View | Access | Purpose |
|---|---|---|---|
| `/matches/` | `job_matches` | Signed-in job seeker with a profile | Recommended approved jobs |
| `/matches/candidates/` | `employer_candidates_index` | Signed-in employer or staff | Pick one of your jobs to rank candidates |
| `/matches/jobs/<job_id>/candidates/` | `job_candidates` | Job owner or staff | Rank candidates for one job |
| `/matches/api/jobs/` | `api_job_matches` | Signed-in job seeker with a profile | JSON job recommendations |
| `/matches/api/jobs/<job_id>/candidates/` | `api_job_candidates` | Job owner or staff | JSON candidate ranking |

The job-seeker pages link from `/dashboard/`. The employer page links from
`/employer-dashboard/`.

## Permissions

- Job-seeker pages require login. A user without a `JobSeekerProfile` is
  redirected to `/profile/create/`.
- Candidate pages require the signed-in user to be:
  - staff, or
  - the owner of the job through `Job.client.user`.
- Other authenticated users receive `403 PermissionDenied`.
- Candidate JSON contains professional profile fields only. It does not expose
  email addresses, phone numbers, or uploaded documents.

## Scoring model

Every match returns a score from 0 to 100 plus six components. Weights must add
up to 100:

| Component | Weight | What it measures |
|---|---:|---|
| Skills | 40 | Overlap between `Job.required_skills` and the seeker's skills, title, profession, and category |
| Role | 25 | Keyword overlap between the job title/category and the seeker's title/profession/category |
| Location | 15 | Same city, overlapping location keywords, or same country with a different city |
| Experience | 10 | Seeker years compared with `Job.experience_required` |
| Verification | 5 | Whether staff have verified the seeker profile |
| Profile completeness | 5 | Presence of title, bio, location, skills, experience, CV, photo, and rate |

### Missing-data behaviour

The engine is intentionally conservative:

- If a job has no `required_skills`, the skills component falls back to
  title/category keywords.
- If a profile has no location, location receives a neutral half score and the
  explanation asks the seeker to add a city.
- If a job has no experience requirement, experience receives full points.
- A missing or unverified profile is explained as a gap rather than hidden.

### Example explanation

A strong match might produce:

```
Matches 4 of 4 required skills: Python, Django, PostgreSQL, REST APIs.
Your professional title aligns closely with this role.
Both are in Addis Ababa, Ethiopia.
5 years of experience meets the 3-year requirement.
Profile verified by Ethiogen.
Profile is 88% complete.
```

A weaker match might produce gaps such as:

```
Missing required skills: Welding.
The job is in Mekelle, Ethiopia; your profile is in Addis Ababa, Ethiopia.
1 years of experience vs 3 required.
Profile is not verified yet.
```

## Ranking

`rank_jobs_for_profile()`:

1. Starts from approved, non-completed jobs.
2. Scores each job.
3. Sorts by score descending, then by posting date.
4. Returns the top 20 by default.

`rank_candidates_for_job()`:

1. Starts from active profiles whose users are active.
2. Scores each profile against the job.
3. Sorts by score, verification, experience, then rating.
4. Returns the top 20 by default.

Scores are computed on demand. There is no persisted `JobMatch` table yet, so
scores never go stale and no migration is required. If the candidate pool grows
large, add a cached model with a job/profile fingerprint and a refresh command;
keep the public service functions as the source of truth.

## JSON examples

### `GET /matches/api/jobs/`

```json
{
  "ok": true,
  "generated_at": "2026-11-13T10:30:00+00:00",
  "count": 1,
  "matches": [
    {
      "job_id": 42,
      "title": "Senior Django Developer",
      "company": "Acme Systems",
      "location": "Addis Ababa, Ethiopia",
      "employment_type": "Full-time",
      "salary": "45000.00",
      "posted_date": "2026-11-12T09:00:00+00:00",
      "url": "/jobs/42/",
      "score": 91,
      "reasons": ["Matches 4 of 4 required skills: Python, Django, PostgreSQL, REST APIs."],
      "gaps": ["Profile is not verified yet."],
      "breakdown": [
        {
          "key": "skills",
          "label": "Skills",
          "points": 40.0,
          "weight": 40,
          "detail": "4/4 required skills matched."
        }
      ]
    }
  ]
}
```

If the user has no profile:

```json
{
  "ok": false,
  "error": "Create a job seeker profile first.",
  "profile_url": "/profile/create/"
}
```

HTTP status is `400`.

### `GET /matches/api/jobs/<job_id>/candidates/`

```json
{
  "ok": true,
  "generated_at": "2026-11-13T10:31:00+00:00",
  "job": {
    "id": 42,
    "title": "Senior Django Developer",
    "company": "Acme Systems",
    "location": "Addis Ababa, Ethiopia",
    "url": "/jobs/42/"
  },
  "count": 1,
  "matches": [
    {
      "profile_id": 7,
      "name": "Sara Kebede",
      "title": "Django Developer",
      "location": "Addis Ababa",
      "experience_years": 5,
      "skills": ["Python", "Django", "PostgreSQL"],
      "hourly_rate": "500.00",
      "verified": true,
      "url": "/profile/7/",
      "score": 91,
      "reasons": ["Matches 3 of 3 required skills: Python, Django, PostgreSQL."],
      "gaps": [],
      "breakdown": []
    }
  ]
}
```

A non-owner receives `403`. The `breakdown` array is abbreviated above for
space; real responses include all six components.

## Configuration and tuning

Weights live in `ai_engine/services.py`:

```python
WEIGHTS = {
    'skills': 40,
    'role': 25,
    'location': 15,
    'experience': 10,
    'verification': 5,
    'completeness': 5,
}
```

Keep the total at 100. After changing weights:

```bash
python manage.py check
python manage.py test ai_engine
```

No migration is needed because scores are computed live.

## Adding a real AI provider later

Keep the public functions stable:

- `calculate_match(profile, job) -> MatchResult`
- `rank_jobs_for_profile(profile, ...)`
- `rank_candidates_for_job(job, ...)`
- `serialize_job_match(result)` and `serialize_candidate(result)`

A provider can generate richer skill extraction, embeddings, or narrative
explanations behind those functions. Preserve the component breakdown so users
and staff can still audit a score. Add cost limits, timeouts, and a fallback to
the deterministic scorer before enabling a paid provider in production.

## Tests

```bash
python manage.py test ai_engine
```

Coverage includes:

- score bounds and component breakdowns,
- missing skills, location mismatch, and experience shortfall explanations,
- verification boost,
- approved-job filtering and active-candidate filtering,
- job-seeker page/API behaviour,
- owner, non-owner, and staff permissions for candidate pages/APIs.

If `.env` points at PostgreSQL and the database user cannot create test
databases, run the suite against SQLite:

```powershell
$env:DB_ENGINE='sqlite'
python manage.py test ai_engine
```

## Current limitations

- Only `jobs.Job` is scored. Telegram `JobPost` matching is a future extension.
- Candidate access uses direct `Job.client` ownership. Tenant workspace roles are
  not yet consulted by this module.
- No persisted scores, pagination, saved matches, or notifications.
- No CV parsing or semantic embeddings yet; matching uses structured profile
  fields and keyword overlap.
- Scores are decision support, not an automated hiring decision.
