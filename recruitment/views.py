from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from jobs.models import Job

from .forms import (
    ApplicationForm,
    ApplicationNoteForm,
    ApplicationStatusForm,
    JobPostingForm,
)
from .models import Application, ApplicationEvent


def _client_profile(user):
    return getattr(user, 'client_profile', None)


def _jobs_for_user(user):
    if user.is_staff:
        return Job.objects.all()
    client = _client_profile(user)
    if client is None:
        return Job.objects.none()
    return Job.objects.filter(client=client)


def _require_job_access(user, job: Job) -> None:
    if user.is_staff:
        return
    client = _client_profile(user)
    if client is None or job.client_id != client.pk:
        raise PermissionDenied('Only the job owner or staff can manage this pipeline.')


# ---------------------------------------------------------------------------
# Public recruitment pages
# ---------------------------------------------------------------------------
@login_required
def create_job_posting(request):
    client = _client_profile(request.user)
    if client is None and not request.user.is_staff:
        messages.error(request, 'Create an employer profile before posting a job.')
        return redirect('jobs:client_profile')

    if request.method == 'POST':
        form = JobPostingForm(request.POST)
        if form.is_valid():
            job = form.save(commit=False)
            job.client = client
            if client and not job.company_name:
                job.company_name = client.company_name
            job.is_approved = False
            job.save()
            form.save_m2m()
            messages.success(
                request,
                'Job submitted for approval. You can track applicants here once it is live.',
            )
            return redirect('recruitment:ats_dashboard')
    else:
        form = JobPostingForm()

    return render(
        request,
        'recruitment/create_job_posting.html',
        {'form': form},
    )


@login_required
def job_postings(request):
    if request.user.is_staff:
        jobs = Job.objects.filter(is_completed=False)
    else:
        jobs = Job.objects.filter(is_approved=True, is_completed=False)

    jobs = jobs.select_related('client').order_by('-posted_date')
    applied_job_ids = set(
        Application.objects
        .filter(applicant=request.user)
        .values_list('job_id', flat=True)
    )

    return render(
        request,
        'recruitment/job_postings.html',
        {'job_postings': jobs, 'applied_job_ids': applied_job_ids},
    )


@login_required
def apply_for_job(request, job_posting_id):
    job = get_object_or_404(
        Job,
        pk=job_posting_id,
        is_approved=True,
        is_completed=False,
    )

    if Application.objects.filter(job=job, applicant=request.user).exists():
        messages.info(request, 'You have already applied for this job.')
        return redirect('recruitment:my_applications')

    if request.method == 'POST':
        form = ApplicationForm(request.POST, request.FILES)
        if form.is_valid():
            application = form.save(commit=False)
            application.job = job
            application.applicant = request.user
            application.save()
            messages.success(request, 'Application submitted.')
            return redirect('recruitment:my_applications')
    else:
        form = ApplicationForm()

    return render(
        request,
        'recruitment/apply_for_job.html',
        {'form': form, 'job_posting': job},
    )


@login_required
def my_applications(request):
    applications = (
        Application.objects
        .filter(applicant=request.user)
        .select_related('job', 'job__client')
        .prefetch_related('events__actor')
        .order_by('-applied_at')
    )
    return render(
        request,
        'recruitment/my_applications.html',
        {'applications': applications},
    )


# ---------------------------------------------------------------------------
# Employer ATS
# ---------------------------------------------------------------------------
@login_required
def ats_dashboard(request):
    jobs = _jobs_for_user(request.user)
    if not request.user.is_staff and _client_profile(request.user) is None:
        raise PermissionDenied('Create an employer profile to use the ATS.')

    jobs = (
        jobs.select_related('client')
        .annotate(
            application_count=Count('applications'),
            submitted_count=Count(
                'applications',
                filter=Q(applications__status=Application.STATUS_SUBMITTED),
            ),
            shortlisted_count=Count(
                'applications',
                filter=Q(applications__status=Application.STATUS_SHORTLISTED),
            ),
            hired_count=Count(
                'applications',
                filter=Q(applications__status=Application.STATUS_HIRED),
            ),
        )
        .order_by('-posted_date')
    )
    return render(
        request,
        'recruitment/ats_dashboard.html',
        {'jobs': jobs},
    )


@login_required
def ats_job_pipeline(request, job_id: int):
    job = get_object_or_404(
        Job.objects.select_related('client'),
        pk=job_id,
    )
    _require_job_access(request.user, job)

    applications = list(
        job.applications
        .select_related('applicant', 'applicant__job_seeker_profile')
        .prefetch_related('events__actor')
        .order_by('-applied_at')
    )
    for application in applications:
        application.seeker_profile = getattr(
            application.applicant, 'job_seeker_profile', None
        )

    labels = dict(Application.STATUS_CHOICES)
    stage_groups = [
        {
            'value': status,
            'label': labels[status],
            'items': [app for app in applications if app.status == status],
        }
        for status in Application.PIPELINE_STATUSES
    ]

    return render(
        request,
        'recruitment/ats_job_pipeline.html',
        {
            'job': job,
            'applications': applications,
            'stage_groups': stage_groups,
        },
    )


@login_required
def ats_application_detail(request, application_id: int):
    application = get_object_or_404(
        Application.objects
        .select_related('job', 'job__client', 'applicant', 'applicant__job_seeker_profile')
        .prefetch_related('events__actor'),
        pk=application_id,
    )
    _require_job_access(request.user, application.job)

    return render(
        request,
        'recruitment/ats_application_detail.html',
        {
            'application': application,
            'seeker_profile': getattr(
                application.applicant, 'job_seeker_profile', None
            ),
            'status_form': ApplicationStatusForm(
                initial={'status': application.status}
            ),
            'note_form': ApplicationNoteForm(),
        },
    )


@login_required
@require_POST
def update_application_status(request, application_id: int):
    application = get_object_or_404(
        Application.objects.select_related('job', 'job__client'),
        pk=application_id,
    )
    _require_job_access(request.user, application.job)

    form = ApplicationStatusForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Choose a valid pipeline status.')
        return redirect('recruitment:ats_application_detail', application_id=application.pk)

    new_status = form.cleaned_data['status']
    if new_status == application.status:
        messages.info(request, 'The application is already in that stage.')
    else:
        application._event_actor = request.user
        application.status = new_status
        application.save(update_fields=['status', 'updated_at'])
        messages.success(request, 'Pipeline stage updated.')

    return redirect('recruitment:ats_application_detail', application_id=application.pk)


@login_required
@require_POST
def add_application_note(request, application_id: int):
    application = get_object_or_404(
        Application.objects.select_related('job', 'job__client'),
        pk=application_id,
    )
    _require_job_access(request.user, application.job)

    form = ApplicationNoteForm(request.POST)
    if form.is_valid():
        note = form.cleaned_data['note'].strip()
        if note:
            ApplicationEvent.objects.create(
                application=application,
                actor=request.user,
                event_type=ApplicationEvent.EVENT_NOTE,
                note=note,
            )
            messages.success(request, 'Note added to the application timeline.')
        else:
            messages.error(request, 'A note cannot be empty.')
    else:
        messages.error(request, 'The note is too long.')

    return redirect('recruitment:ats_application_detail', application_id=application.pk)
