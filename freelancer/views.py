from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .forms import FreelancerProfileForm, JobPostingForm, BidForm
from .models import FreelancerProfile, JobPosting, Bid
from django.contrib import messages
from django.shortcuts import get_object_or_404

@login_required
def freelancer_profile(request):
    if request.method == 'POST':
        form = FreelancerProfileForm(request.POST, request.FILES, instance=request.user.freelancerprofile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Freelancer profile updated successfully!')
            return redirect('freelancer_profile')
    else:
        form = FreelancerProfileForm(instance=request.user.freelancerprofile)
    return render(request, 'freelancer_app/profile.html', {'form': form})

@login_required
def create_job_posting(request):
    if request.method == 'POST':
        form = JobPostingForm(request.POST)
        if form.is_valid():
            job_posting = form.save(commit=False)
            job_posting.created_by = request.user
            job_posting.save()
            messages.success(request, 'Job posting created successfully!')
            return redirect('job_list')  # Assuming a 'job_list' URL exists
    else:
        form = JobPostingForm()
    return render(request, 'freelancer_app/create_job.html', {'form': form})

@login_required
def job_detail(request, job_id):
    job_posting = get_object_or_404(JobPosting, id=job_id)
    bids = Bid.objects.filter(job_posting=job_posting)
    return render(request, 'freelancer_app/job_detail.html', {'job_posting': job_posting, 'bids': bids})
def list_freelancing_job(request):
      jobs = JobPosting.objects.all()
      return render(request, 'freelancer_app/list_freelancing_jobs.html', {'jobs': jobs})
@login_required
def place_bid(request, job_id):
    job_posting = get_object_or_404(JobPosting, id=job_id)
    if request.method == 'POST':
        form = BidForm(request.POST)
        if form.is_valid():
            bid = form.save(commit=False)
            bid.freelancer = request.user
            bid.job_posting = job_posting
            bid.save()
            messages.success(request, 'Bid placed successfully!')
            return redirect('job_detail', job_id=job_id)
    else:
        form = BidForm()
    return render(request, 'freelancer_app/place_bid.html', {'form': form, 'job_posting': job_posting})
