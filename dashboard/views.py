"""Professional custom admin dashboard views."""
from __future__ import annotations

from decimal import Decimal

from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.db.models import Count, Sum
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from billing.models import ChannelPost, Subscription, PostApplication
from billing import services
from jobs.models import JobPost, JobSeekerProfile, ClientProfile
from tenants.models import Organization


def _staff(u):
    return u.is_authenticated and u.is_staff


login_staff = [login_required, user_passes_test(_staff)]


def _wrap(view):
    for d in reversed(login_staff):
        view = d(view)
    return view


def _ctx(request, **extra):
    from django.contrib.auth import get_user_model

    counts = {
        'users': get_user_model().objects.count(),
        'job_seekers': JobSeekerProfile.objects.count(),
        'clients': ClientProfile.objects.count(),
        'jobs': JobPost.objects.count(),
        'organizations': Organization.objects.count(),
        'active_tenants': Organization.objects.filter(status='active').count(),
        'channel_posts': ChannelPost.objects.count(),
        'published_posts': ChannelPost.objects.filter(status=ChannelPost.STATUS_PUBLISHED).count(),
        'subscriptions': Subscription.objects.count(),
        'active_subs': Subscription.objects.filter(status=Subscription.STATUS_ACTIVE).count(),
        'pending_subs': Subscription.objects.filter(status=Subscription.STATUS_PENDING_REVIEW).count(),
        'applications': PostApplication.objects.count(),
    }
    try:
        counts['revenue'] = Subscription.objects.filter(
            status=Subscription.STATUS_ACTIVE
        ).aggregate(s=Sum('amount'))['s'] or Decimal('0')
    except Exception:
        counts['revenue'] = Decimal('0')
    base = {'counts': counts, 'now': timezone.now(), 'user': request.user}
    base.update(extra)
    return base


@_wrap
def home(request: HttpRequest) -> HttpResponse:
    recent_subs = Subscription.objects.select_related('user').order_by('-created_at')[:8]
    recent_posts = ChannelPost.objects.order_by('-created_at')[:8]
    recent_apps = PostApplication.objects.select_related('post', 'applicant').order_by('-created_at')[:8]
    recent_orgs = Organization.objects.order_by('-created_at')[:8]
    return render(request, 'dashboard/home.html', _ctx(request,
        recent_subs=recent_subs, recent_posts=recent_posts,
        recent_apps=recent_apps, recent_orgs=recent_orgs,
    ))


@_wrap
def subscriptions(request: HttpRequest) -> HttpResponse:
    qs = Subscription.objects.select_related('user').order_by('-created_at')
    status = request.GET.get('status', '').strip()
    q = request.GET.get('q', '').strip()
    if status:
        qs = qs.filter(status=status)
    if q:
        qs = qs.filter(user__username__icontains=q) | qs.filter(user__email__icontains=q)
    paginator = Paginator(qs, 25)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'dashboard/subscriptions.html', _ctx(request,
        page=page, status=status, q=q,
        status_choices=Subscription.STATUS_CHOICES,
    ))


@_wrap
@require_POST
def subscription_action(request: HttpRequest, pk: int, action: str) -> HttpResponse:
    sub = get_object_or_404(Subscription, pk=pk)
    if action == 'approve':
        services.activate_subscription(sub, reviewed_by=request.user, note='Approved from dashboard.')
    elif action == 'reject':
        services.reject_subscription(sub, reviewed_by=request.user, note='Rejected from dashboard.')
    return redirect('dashboard:subscriptions')


@_wrap
def posts(request: HttpRequest) -> HttpResponse:
    qs = ChannelPost.objects.order_by('-created_at')
    status = request.GET.get('status', '').strip()
    kind = request.GET.get('kind', '').strip()
    q = request.GET.get('q', '').strip()
    if status:
        qs = qs.filter(status=status)
    if kind:
        qs = qs.filter(kind=kind)
    if q:
        qs = qs.filter(title__icontains=q)
    paginator = Paginator(qs, 25)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'dashboard/posts.html', _ctx(request,
        page=page, status=status, kind=kind, q=q,
        status_choices=ChannelPost.STATUS_CHOICES,
        kind_choices=ChannelPost.KIND_CHOICES,
    ))


@_wrap
@require_POST
def post_publish(request: HttpRequest, pk: int) -> HttpResponse:
    post = get_object_or_404(ChannelPost, pk=pk)
    services.publish_post(post)
    return redirect('dashboard:posts')


@_wrap
def users(request: HttpRequest) -> HttpResponse:
    from django.contrib.auth import get_user_model

    User = get_user_model()
    qs = User.objects.order_by('-date_joined')
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(username__icontains=q) | qs.filter(email__icontains=q)
    paginator = Paginator(qs, 25)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'dashboard/users.html', _ctx(request, page=page, q=q))


@_wrap
def organizations(request: HttpRequest) -> HttpResponse:
    qs = Organization.objects.order_by('-created_at')
    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()
    if q:
        qs = qs.filter(name__icontains=q) | qs.filter(slug__icontains=q)
    if status:
        qs = qs.filter(status=status)
    paginator = Paginator(qs, 25)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'dashboard/organizations.html', _ctx(request,
        page=page, q=q, status=status,
    ))


@_wrap
def job_seekers(request: HttpRequest) -> HttpResponse:
    qs = JobSeekerProfile.objects.select_related('user', 'profession').order_by('-id')
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(user__username__icontains=q) | qs.filter(title__icontains=q)
    paginator = Paginator(qs, 25)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'dashboard/job_seekers.html', _ctx(request, page=page, q=q))


@_wrap
def applications(request: HttpRequest) -> HttpResponse:
    qs = PostApplication.objects.select_related('post', 'applicant').order_by('-created_at')
    status = request.GET.get('status', '').strip()
    if status:
        qs = qs.filter(status=status)
    paginator = Paginator(qs, 25)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'dashboard/applications.html', _ctx(request,
        page=page, status=status,
        status_choices=PostApplication.STATUS_CHOICES,
    ))


def _settings_row():
    from billing.models import IntegrationSettings

    row = IntegrationSettings.load()
    if row is None:
        row = IntegrationSettings()
        row.save()
    return row


SECTION_FIELDS = {
    'telegram': [
        'telegram_bot_token', 'telegram_bot_username', 'telegram_channel_id',
        'telegram_channel_username', 'telegram_group_id', 'telegram_admin_ids',
        'telegram_website_url',
    ],
    'chapa': [
        'chapa_enabled', 'chapa_public_key', 'chapa_secret_key', 'chapa_api_base',
        'chapa_auto_approve', 'chapa_webhook_url',
    ],
    'telebirr': [
        'telebirr_enabled', 'telebirr_name', 'telebirr_phone', 'telebirr_api_base',
        'telebirr_api_key', 'telebirr_merchant_id', 'telebirr_return_url',
    ],
    'bank': [
        'bank_enabled', 'bank_name', 'bank_account_name', 'bank_account_number',
    ],
    'subscription': [
        'currency', 'subscription_price', 'subscription_days', 'payment_instructions',
    ],
    'branding': [
        'logo_wordmark', 'logo_show_caption', 'logo_height_px',
    ],
    'facebook': [
        'facebook_enabled', 'facebook_page_id', 'facebook_page_name',
        'facebook_page_access_token', 'facebook_api_version', 'facebook_default_link',
    ],
    'site': ['site_url', 'notes'],
}


@_wrap
def settings_view(request: HttpRequest) -> HttpResponse:
    from billing import config

    row = _settings_row()
    return render(request, 'dashboard/settings.html', _ctx(request, row=row, report=config.configuration_report()))


@_wrap
@require_POST
def settings_save(request: HttpRequest) -> HttpResponse:
    from billing import config

    row = _settings_row()
    section = request.POST.get('section', '').strip()
    fields = SECTION_FIELDS.get(section, [])
    for f in fields:
        if f in ('chapa_enabled', 'chapa_auto_approve', 'telebirr_enabled',
                 'bank_enabled', 'facebook_enabled', 'logo_show_caption'):
            setattr(row, f, request.POST.get(f) in ('on', '1', 'true', 'True'))
        else:
            val = request.POST.get(f, '')
            # numeric handling
            if f == 'logo_height_px':
                try:
                    val = int(val or 0)
                except ValueError:
                    val = row.logo_height_px
            if f == 'subscription_price':
                from decimal import Decimal

                try:
                    val = Decimal(val)
                except Exception:
                    val = row.subscription_price
            if f == 'subscription_days':
                try:
                    val = int(val or 0)
                except ValueError:
                    val = row.subscription_days
            setattr(row, f, val)
    row.save()
    try:
        config.invalidate_cache()
    except Exception:
        pass
    from django.contrib import messages

    messages.success(request, f'{section.title()} settings saved.')
    return redirect('dashboard:settings')