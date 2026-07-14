from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required

from jobs.models import Job
from .models import Application
from .forms import JobPostingForm, ApplicationForm


@login_required
def create_job_posting(request):
    if request.method == "POST":
        form = JobPostingForm(request.POST)

        if form.is_valid():
            job = form.save(commit=False)
            job.created_by = request.user
            job.save()

            return redirect('job_postings')
    else:
        form = JobPostingForm()

    return render(
        request,
        'recruitment/create_job_posting.html',
        {'form': form}
    )


@login_required
def job_postings(request):
    jobs = Job.objects.all()

    return render(
        request,
        'recruitment/job_postings.html',
        {'job_postings': jobs}
    )


@login_required
def apply_for_job(request, job_posting_id):
    job = get_object_or_404(Job, pk=job_posting_id)

    if request.method == "POST":
        form = ApplicationForm(
            request.POST,
            request.FILES
        )

        if form.is_valid():
            application = form.save(commit=False)
            application.job = job
            application.applicant = request.user
            application.save()

            return redirect('job_postings')
    else:
        form = ApplicationForm()

    return render(
        request,
        'recruitment/apply_for_job.html',
        {
            'form': form,
            'job_posting': job
        }
    )