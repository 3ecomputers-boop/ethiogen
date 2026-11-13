"""Views for the explainable matching engine.

The HTML pages are intentionally small and self-contained. The JSON endpoints
expose the same results for a future mobile client or Mini App.
"""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET

from jobs.models import Job

from .services import (
    rank_candidates_for_job,
    rank_jobs_for_profile,
    serialize_candidate,
    serialize_job_match,
)


def _get_seeker_profile(user):
    """Return the user's seeker profile, or ``None`` if they have not made one."""
    return getattr(user, 'job_seeker_profile', None)


def _get_client_profile(user):
    return getattr(user, 'client_profile', None)


def _can_view_candidates(user, job: Job) -> bool:
    if user.is_staff:
        return True
    client = _get_client_profile(user)
    return bool(client and job.client_id == client.pk)


def _require_candidate_access(user, job: Job) -> None:
    if not _can_view_candidates(user, job):
        raise PermissionDenied('Only the job owner or staff can view candidate matches.')


@login_required
def job_matches(request):
    """Recommend approved jobs to the signed-in job seeker."""
    profile = _get_seeker_profile(request.user)
    if profile is None:
        messages.info(
            request,
            'Create a job seeker profile so we can calculate your matches.',
        )
        return redirect('jobs:create_job_seeker_profile')

    matches = rank_jobs_for_profile(profile, limit=20)
    return render(
        request,
        'ai_engine/job_matches.html',
        {'profile': profile, 'matches': matches},
    )


@login_required
@require_GET
def api_job_matches(request):
    """JSON: top job matches for the signed-in job seeker."""
    profile = _get_seeker_profile(request.user)
    if profile is None:
        return JsonResponse(
            {
                'ok': False,
                'error': 'Create a job seeker profile first.',
                'profile_url': reverse('jobs:create_job_seeker_profile'),
            },
            status=400,
        )

    matches = rank_jobs_for_profile(profile, limit=20)
    return JsonResponse({
        'ok': True,
        'generated_at': timezone.now().isoformat(),
        'count': len(matches),
        'matches': [serialize_job_match(match) for match in matches],
    })


@login_required
def employer_candidates_index(request):
    """List the employer's jobs so they can open candidate rankings."""
    if request.user.is_staff:
        jobs = Job.objects.all()
    else:
        client = _get_client_profile(request.user)
        if client is None:
            raise PermissionDenied('Create an employer profile to rank candidates.')
        jobs = Job.objects.filter(client=client)

    jobs = (
        jobs.select_related('client')
        .prefetch_related('required_skills')
        .order_by('-posted_date')[:100]
    )
    return render(
        request,
        'ai_engine/employer_candidates.html',
        {'jobs': jobs},
    )


@login_required
def job_candidates(request, job_id: int):
    """Rank job seekers for one job. Visible to the job owner and staff only."""
    job = get_object_or_404(
        Job.objects.select_related('client').prefetch_related('required_skills'),
        pk=job_id,
    )
    _require_candidate_access(request.user, job)

    matches = rank_candidates_for_job(job, limit=20)
    return render(
        request,
        'ai_engine/job_candidates.html',
        {'job': job, 'matches': matches},
    )


@login_required
@require_GET
def api_job_candidates(request, job_id: int):
    """JSON: top candidate matches for one job."""
    job = get_object_or_404(
        Job.objects.select_related('client').prefetch_related('required_skills'),
        pk=job_id,
    )
    _require_candidate_access(request.user, job)

    matches = rank_candidates_for_job(job, limit=20)
    return JsonResponse({
        'ok': True,
        'generated_at': timezone.now().isoformat(),
        'job': {
            'id': job.pk,
            'title': job.title,
            'company': job.company_name,
            'location': job.location,
            'url': job.get_absolute_url(),
        },
        'count': len(matches),
        'matches': [serialize_candidate(match) for match in matches],
    })
