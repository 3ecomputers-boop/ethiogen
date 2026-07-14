from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from django.contrib.auth import get_user_model

User = get_user_model()
from .models import Job, JobSeekerProfile, ClientProfile, HireRequest, Talent

@staff_member_required
def staff_dashboard(request):
    """Admin dashboard with platform metrics."""
    context = {
        'total_users': User.objects.count(),
        'total_jobs': Job.objects.count(),
        'total_talents': Talent.objects.count(),
        'total_job_seekers': JobSeekerProfile.objects.count(),
        'total_clients': ClientProfile.objects.count(),
        'pending_jobs': Job.objects.filter(is_approved=False).count(),
        'total_hire_requests': HireRequest.objects.count(),
        'recent_users': User.objects.order_by('-date_joined')[:5],
        'recent_jobs': Job.objects.order_by('-posted_date')[:5],
    }
    return render(request, 'admin/staff_dashboard.html', context)