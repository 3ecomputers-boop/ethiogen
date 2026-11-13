"""Explainable, rules-based job matching.

The engine compares the data already stored on ``JobSeekerProfile`` with a
``Job`` and returns a 0-100 score, the component breakdown, plain-language
reasons, and gaps. It is deterministic and auditable, so it can run without
an external AI provider.

An LLM/embedding provider can be layered on later behind this interface; the
current implementation is deliberately transparent and cheap to run.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Sequence

from django.urls import reverse

from jobs.models import Job, JobSeekerProfile

# Component weights. They must add up to 100.
WEIGHTS = {
    'skills': 40,
    'role': 25,
    'location': 15,
    'experience': 10,
    'verification': 5,
    'completeness': 5,
}

STOPWORDS = frozenset({
    'a', 'an', 'and', 'at', 'for', 'in', 'of', 'on', 'or', 'the', 'to',
    'with', 'from', 'by', 'as', 'is', 'are', 'be', 'this', 'that',
})

_WORD_RE = re.compile(r'[^a-z0-9+#.]+')


@dataclass(frozen=True)
class MatchComponent:
    """One weighted part of a match score."""

    key: str
    label: str
    weight: int
    ratio: float
    detail: str

    @property
    def points(self) -> float:
        return round(self.weight * max(0.0, min(1.0, self.ratio)), 1)


@dataclass(frozen=True)
class MatchResult:
    """A scored profile/job pair with an explanation."""

    profile: JobSeekerProfile
    job: Job
    score: int
    components: tuple[MatchComponent, ...]
    reasons: tuple[str, ...]
    gaps: tuple[str, ...]

    @property
    def breakdown(self) -> tuple[MatchComponent, ...]:
        """Template-friendly alias for ``components``."""
        return self.components


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------
def _normalise(value: object) -> str:
    return _WORD_RE.sub(' ', str(value or '').lower()).strip()


def _tokens(value: object) -> list[str]:
    return [
        token for token in _normalise(value).split()
        if token and token not in STOPWORDS
    ]


def _as_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(',') if item.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def _related_name(obj: object, attr: str) -> str:
    related = getattr(obj, attr, None)
    return str(getattr(related, 'name', '') or '')


def _filled(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict, set)):
        return bool(value)
    try:
        return bool(value)
    except (TypeError, ValueError):
        return False


def _term_in(term: str, haystack: str) -> bool:
    """Whether a skill/term occurs in a normalised haystack.

    Token matching avoids the classic ``Java`` in ``JavaScript`` false
    positive. Multi-word terms match when any meaningful word overlaps.
    """
    normalised = _normalise(term)
    if not normalised:
        return False
    haystack_tokens = set(haystack.split())
    term_tokens = set(normalised.split())
    if not term_tokens:
        return False
    return bool(term_tokens & haystack_tokens)


def _unique(items: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        clean = item.strip()
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return tuple(result)


# ---------------------------------------------------------------------------
# Component scoring
# ---------------------------------------------------------------------------
def _profile_skill_haystack(profile: JobSeekerProfile) -> str:
    parts = [
        * _as_list(profile.skills),
        profile.title,
        _related_name(profile, 'profession'),
        _related_name(profile, 'category'),
        _related_name(profile, 'subcategory'),
    ]
    return _normalise(' '.join(part for part in parts if part))


def _skills_component(
    profile: JobSeekerProfile,
    job: Job,
) -> tuple[MatchComponent, list[str], list[str]]:
    # ``str(Profession)`` returns the profession name.
    required = [
        str(skill).strip()
        for skill in job.required_skills.all()
        if str(skill).strip()
    ]
    haystack = _profile_skill_haystack(profile)

    reasons: list[str] = []
    gaps: list[str] = []

    if required:
        matched = [skill for skill in required if _term_in(skill, haystack)]
        ratio = len(matched) / len(required)
        if matched:
            reasons.append(
                'Matches %d of %d required skills: %s.'
                % (len(matched), len(required), ', '.join(matched[:6]))
            )
        missing = [skill for skill in required if skill not in matched]
        if missing:
            gaps.append('Missing required skills: %s.' % ', '.join(missing[:6]))
        detail = '%d/%d required skills matched.' % (len(matched), len(required))
        return MatchComponent('skills', 'Skills', WEIGHTS['skills'], ratio, detail), reasons, gaps

    # No explicit skill list: fall back to title/category keywords.
    job_terms = _tokens(' '.join([job.title, job.category]))
    profile_terms = set(_tokens(' '.join([
        profile.title,
        _related_name(profile, 'profession'),
        _related_name(profile, 'category'),
        ' '.join(_as_list(profile.skills)),
    ])))
    if job_terms:
        matched = [term for term in job_terms if term in profile_terms]
        ratio = min(1.0, len(matched) / len(set(job_terms)))
        detail = 'No required-skill list; matched role keywords.'
        if matched:
            reasons.append('Role keywords overlap: %s.' % ', '.join(matched[:6]))
        else:
            gaps.append('No role keywords overlap yet; add skills or a clearer title.')
        return MatchComponent('skills', 'Skills', WEIGHTS['skills'], ratio, detail), reasons, gaps

    return (
        MatchComponent('skills', 'Skills', WEIGHTS['skills'], 0.5, 'No skills or role keywords to compare.'),
        reasons,
        gaps,
    )


def _role_component(
    profile: JobSeekerProfile,
    job: Job,
) -> tuple[MatchComponent, list[str], list[str]]:
    profile_terms = set(_tokens(' '.join([
        profile.title,
        _related_name(profile, 'profession'),
        _related_name(profile, 'category'),
        _related_name(profile, 'subcategory'),
    ])))
    job_terms = set(_tokens(' '.join([job.title, job.category])))

    reasons: list[str] = []
    gaps: list[str] = []

    if not job_terms:
        return (
            MatchComponent('role', 'Role', WEIGHTS['role'], 0.5, 'Job has no title/category keywords.'),
            reasons,
            gaps,
        )

    overlap = sorted(job_terms & profile_terms)
    ratio = len(overlap) / len(job_terms)

    if ratio >= 0.75:
        reasons.append('Your professional title aligns closely with this role.')
    elif overlap:
        reasons.append('Some role keywords overlap: %s.' % ', '.join(overlap[:5]))
    else:
        gaps.append('Your profile title does not overlap with the job title yet.')

    detail = '%d/%d role keywords matched.' % (len(overlap), len(job_terms))
    return MatchComponent('role', 'Role', WEIGHTS['role'], ratio, detail), reasons, gaps


def _country_name(profile: JobSeekerProfile) -> str:
    country = getattr(profile, 'country', '')
    if not country:
        return ''
    return str(getattr(country, 'name', '') or country)


def _location_component(
    profile: JobSeekerProfile,
    job: Job,
) -> tuple[MatchComponent, list[str], list[str]]:
    profile_location = _normalise(' '.join(filter(None, [profile.city, profile.location])))
    job_location = _normalise(job.location)
    country = _normalise(_country_name(profile))

    reasons: list[str] = []
    gaps: list[str] = []

    if not job_location:
        return (
            MatchComponent('location', 'Location', WEIGHTS['location'], 0.5, 'Job has no location.'),
            reasons,
            gaps,
        )

    if not profile_location:
        gaps.append('Add your city/location to improve location matching.')
        return (
            MatchComponent('location', 'Location', WEIGHTS['location'], 0.5, 'Your location is missing.'),
            reasons,
            gaps,
        )

    if profile_location in job_location or job_location in profile_location:
        reasons.append('Both are in %s.' % job.location)
        return (
            MatchComponent('location', 'Location', WEIGHTS['location'], 1.0, 'Same location.'),
            reasons,
            gaps,
        )

    profile_tokens = set(profile_location.split()) - STOPWORDS
    job_tokens = set(job_location.split()) - STOPWORDS
    country_tokens = set(country.split()) if country else set()
    shared_tokens = (profile_tokens & job_tokens) - country_tokens
    if shared_tokens:
        reasons.append('Your location overlaps with %s.' % job.location)
        return (
            MatchComponent('location', 'Location', WEIGHTS['location'], 0.8, 'Location keywords overlap.'),
            reasons,
            gaps,
        )

    if country and country in job_location:
        reasons.append('Both are in %s; the city differs.' % country.title())
        gaps.append(
            'The job is in %s; your profile is in %s.'
            % (job.location, profile.city or profile.location)
        )
        return (
            MatchComponent('location', 'Location', WEIGHTS['location'], 0.5, 'Same country, different city.'),
            reasons,
            gaps,
        )

    gaps.append('The job is in %s; your profile is in %s.' % (job.location, profile.city or profile.location))
    return (
        MatchComponent('location', 'Location', WEIGHTS['location'], 0.0, 'Different location.'),
        reasons,
        gaps,
    )


def _experience_component(
    profile: JobSeekerProfile,
    job: Job,
) -> tuple[MatchComponent, list[str], list[str]]:
    required = max(0, int(job.experience_required or 0))
    have = max(0, int(profile.years_of_experience or 0))
    reasons: list[str] = []
    gaps: list[str] = []

    if required == 0:
        reasons.append('No specific experience requirement.')
        return (
            MatchComponent('experience', 'Experience', WEIGHTS['experience'], 1.0, 'No requirement.'),
            reasons,
            gaps,
        )
    if have >= required:
        reasons.append('%d years of experience meets the %d-year requirement.' % (have, required))
        return (
            MatchComponent('experience', 'Experience', WEIGHTS['experience'], 1.0, 'Requirement met.'),
            reasons,
            gaps,
        )

    ratio = have / required
    gaps.append('%d years of experience vs %d required.' % (have, required))
    return (
        MatchComponent('experience', 'Experience', WEIGHTS['experience'], ratio, 'Experience shortfall.'),
        reasons,
        gaps,
    )


def _verification_component(
    profile: JobSeekerProfile,
    job: Job,
) -> tuple[MatchComponent, list[str], list[str]]:
    reasons: list[str] = []
    gaps: list[str] = []
    if profile.is_verified:
        reasons.append('Profile verified by Ethiogen.')
        ratio = 1.0
        detail = 'Verified profile.'
    else:
        gaps.append('Profile is not verified yet.')
        ratio = 0.0
        detail = 'Verification pending.'
    return MatchComponent('verification', 'Verification', WEIGHTS['verification'], ratio, detail), reasons, gaps


def _completeness_component(
    profile: JobSeekerProfile,
    job: Job,
) -> tuple[MatchComponent, list[str], list[str]]:
    checks = [
        ('professional title', profile.title),
        ('bio', profile.bio),
        ('location', profile.city or profile.location),
        ('skills', profile.skills),
        ('experience', profile.years_of_experience),
        ('CV', profile.resume),
        ('photo', profile.profile_picture),
        ('rate', profile.hourly_rate),
    ]
    filled = sum(1 for _label, value in checks if _filled(value))
    ratio = filled / len(checks)
    reasons: list[str] = []
    gaps: list[str] = []

    if ratio >= 0.75:
        reasons.append('Profile is %d%% complete.' % round(ratio * 100))
    else:
        missing = [label for label, value in checks if not _filled(value)]
        gaps.append('Complete more profile fields: %s.' % ', '.join(missing[:5]))

    return (
        MatchComponent(
            'completeness', 'Profile completeness', WEIGHTS['completeness'], ratio,
            '%d/%d profile fields completed.' % (filled, len(checks)),
        ),
        reasons,
        gaps,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def calculate_match(profile: JobSeekerProfile, job: Job) -> MatchResult:
    """Score one profile against one job and explain the result."""
    components: list[MatchComponent] = []
    reasons: list[str] = []
    gaps: list[str] = []

    for scorer in (
        _skills_component,
        _role_component,
        _location_component,
        _experience_component,
        _verification_component,
        _completeness_component,
    ):
        component, component_reasons, component_gaps = scorer(profile, job)
        components.append(component)
        reasons.extend(component_reasons)
        gaps.extend(component_gaps)

    score = int(round(sum(component.points for component in components)))
    score = max(0, min(100, score))

    return MatchResult(
        profile=profile,
        job=job,
        score=score,
        components=tuple(components),
        reasons=_unique(reasons)[:6],
        gaps=_unique(gaps)[:6],
    )


def rank_jobs_for_profile(
    profile: JobSeekerProfile,
    limit: int | None = 20,
    jobs: Sequence[Job] | None = None,
) -> list[MatchResult]:
    """Return approved, open jobs ordered by match score."""
    if jobs is None:
        jobs = (
            Job.objects
            .filter(is_approved=True, is_completed=False)
            .select_related('client')
            .prefetch_related('required_skills')
        )

    results = [calculate_match(profile, job) for job in jobs]
    results.sort(key=lambda result: (
        -result.score,
        -(result.job.posted_date.timestamp() if result.job.posted_date else 0),
    ))
    return results[:limit] if limit is not None else results


def rank_candidates_for_job(
    job: Job,
    limit: int | None = 20,
    profiles: Sequence[JobSeekerProfile] | None = None,
) -> list[MatchResult]:
    """Return active job seekers ordered by match score for one job."""
    if profiles is None:
        profiles = (
            JobSeekerProfile.objects
            .filter(is_active=True, user__is_active=True)
            .select_related('user', 'profession', 'category', 'subcategory')
        )

    results = [calculate_match(profile, job) for profile in profiles]
    results.sort(key=lambda result: (
        -result.score,
        -int(bool(result.profile.is_verified)),
        -(result.profile.years_of_experience or 0),
        -float(result.profile.average_rating or 0),
    ))
    return results[:limit] if limit is not None else results


def serialize_job_match(result: MatchResult) -> dict:
    job = result.job
    return {
        'job_id': job.pk,
        'title': job.title,
        'company': job.company_name,
        'location': job.location,
        'employment_type': job.employment_type,
        'salary': str(job.salary) if job.salary is not None else None,
        'posted_date': job.posted_date.isoformat() if job.posted_date else None,
        'url': reverse('jobs:job_details', args=[job.pk]),
        'score': result.score,
        'reasons': list(result.reasons),
        'gaps': list(result.gaps),
        'breakdown': [
            {
                'key': component.key,
                'label': component.label,
                'points': component.points,
                'weight': component.weight,
                'detail': component.detail,
            }
            for component in result.components
        ],
    }


def serialize_candidate(result: MatchResult) -> dict:
    profile = result.profile
    return {
        'profile_id': profile.pk,
        'name': profile.user.get_full_name() or profile.user.username,
        'title': profile.title,
        'location': profile.city or profile.location,
        'experience_years': profile.years_of_experience or 0,
        'skills': _as_list(profile.skills)[:12],
        'hourly_rate': str(profile.hourly_rate) if profile.hourly_rate else None,
        'verified': bool(profile.is_verified),
        'url': reverse('jobs:view_job_seeker_profile', args=[profile.pk]),
        'score': result.score,
        'reasons': list(result.reasons),
        'gaps': list(result.gaps),
        'breakdown': [
            {
                'key': component.key,
                'label': component.label,
                'points': component.points,
                'weight': component.weight,
                'detail': component.detail,
            }
            for component in result.components
        ],
    }
