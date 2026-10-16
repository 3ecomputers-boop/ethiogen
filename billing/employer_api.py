"""
Employer-facing API for the mini app.

    POST /api/employer/post-job/          create + publish a job to the channel
    GET  /api/employer/my-posts/           list this employer's posts
    GET  /api/employer/applications/       applicants across their posts
    POST /api/employer/applications/<id>/  shortlist / reject an applicant

All endpoints require an authenticated session and reject job seekers, so an
employer account cannot be used to spam the channel.
"""
from __future__ import annotations

import json
import logging
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, JsonResponse
from django.utils import timezone

from django.views.decorators.csrf import csrf_exempt

from billing.models import ChannelPost, PostApplication, Subscription
from billing.services import has_active_subscription, publish_post
from jobs.models import ClientProfile, JobPost
from tenants import provisioning as tenant_provisioning
from tenants import services as tenant_services
from tenants.models import Membership, TenantAuditLog

logger = logging.getLogger(__name__)


def _ambiguous_workspace_response(exc) -> JsonResponse:
    """409 for an employer who belongs to more than one workspace."""
    return JsonResponse({
        'success': False,
        'error': 'This account belongs to more than one organization. '
                 'Send organization_slug to choose one.',
        'code': 'choose_organization',
        'organizations': [
            {'slug': o.slug, 'name': o.name} for o in exc.organizations
        ],
    }, status=409)


def _body(request: HttpRequest) -> dict:
    try:
        return json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        return {}


def _client_profile(user):
    return ClientProfile.objects.filter(user=user).first()


def _is_employer(user) -> bool:
    """
    Who may use the employer tools.

    Historically this meant "has a ClientProfile". That is now too narrow:
    somebody can be invited into a company's workspace without ever
    registering a company of their own, and they are still an employer
    employee. Membership in a workspace is the stronger signal, so accept
    either. A job seeker with no workspace and no company still cannot
    reach these endpoints.
    """
    if not user.is_authenticated:
        return False
    if ClientProfile.objects.filter(user=user).exists():
        return True
    return Membership.objects.filter(user=user, is_active=True).exists()


def _employer_guard(request: HttpRequest):
    """Return (profile, error_response)."""
    user = request.user
    if not user.is_authenticated:
        return None, JsonResponse(
            {'success': False, 'error': 'Sign in as an employer first.'}, status=401
        )
    profile = _client_profile(user)
    if profile is None:
        return None, JsonResponse(
            {'success': False,
             'error': 'Only employer accounts can post jobs.'},
            status=403,
        )
    return profile, None


def _can_post(user) -> tuple:
    """
    Employers need an active subscription to post, same as talent need one
    to apply. Returns (allowed, message).
    """
    if has_active_subscription(user):
        return True, ''
    from billing import config

    price = config.subscription_price()
    return False, (
        f'An active subscription is required to post a job '
        f'({price} {config.currency()}).'
    )


# ======================================================================
# Create + publish a job
# ======================================================================
@csrf_exempt
@login_required
def employer_post_job(request: HttpRequest) -> JsonResponse:
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)

    profile, denied = _employer_guard(request)
    if denied:
        return denied

    allowed, why = _can_post(request.user)
    if not allowed:
        return JsonResponse({'success': False, 'error': why}, status=402)

    data = _body(request)
    title = (data.get('title') or '').strip()
    description = (data.get('description') or '').strip()
    location = (data.get('location') or profile.location or '').strip()
    budget = (data.get('budget') or '').strip()
    category_tag = (data.get('category_tag') or '').strip()
    deadline = (data.get('deadline') or '').strip()

    if not title:
        return JsonResponse({'success': False, 'error': 'Title is required'}, status=400)
    if not description:
        return JsonResponse(
            {'success': False, 'error': 'Description is required'}, status=400
        )

    # --- which tenant does this post belong to? ----------------------
    # A workspace is provisioned on first use so every employer post is
    # governed by a plan and a quota.
    try:
        organization, org_created = tenant_provisioning.resolve_workspace(
            request.user,
            requested_slug=(data.get('organization_slug') or '').strip() or None,
            client_profile=profile,
        )
    except tenant_provisioning.NeedsExplicitOrganization as exc:
        return _ambiguous_workspace_response(exc)
    except PermissionDenied as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=403)

    # --- optional JobPost record so it shows up in the normal job system ---
    job_post = None
    try:
        from decimal import Decimal, InvalidOperation

        amount = Decimal(budget.replace(',', '')) if budget else Decimal('0')
    except Exception:
        amount = Decimal('0')

    deadline_date = None
    if deadline:
        try:
            deadline_date = timezone.datetime.strptime(deadline, '%Y-%m-%d').date()
        except ValueError:
            deadline_date = (timezone.now().date() + timedelta(days=30))

    if profile.company_name:
        try:
            job_post = JobPost.objects.create(
                client=profile,
                organization=organization,
                title=title,
                description=description,
                budget=amount,
                location=location or 'Ethiopia',
                deadline=deadline_date or (timezone.now().date() + timedelta(days=30)),
            )
        except Exception as exc:
            logger.error('JobPost create failed: %s', exc)
            job_post = None

    # --- the channel post (this is what gets published) ---
    post = ChannelPost.objects.create(
        kind=ChannelPost.KIND_JOB,
        title=title,
        body=description,
        company=profile.company_name or organization.name,
        category_tag=category_tag,
        location=location,
        salary=budget,
        deadline=(timezone.datetime.combine(deadline_date, timezone.datetime.min.time())
                  if deadline_date else None),
        source_url=data.get('source_url', '') or '',
        show_apply=True,
        show_subscribe=True,
        created_by=request.user,
        employer=request.user,
        organization=organization,
        job_post=job_post,
    )

    result = publish_post(post)
    post.refresh_from_db()

    if not result.get('ok'):
        # Quota/policy refusal is a billing outcome (402), not a transport
        # failure (502). Do not leave a half-created JobPost behind.
        if result.get('quota_blocked'):
            if job_post is not None:
                job_post.delete()
            TenantAuditLog.record(
                organization, request.user, 'job_post.quota_blocked',
                obj=post, reason=result.get('error'),
            )
            return JsonResponse({
                'success': False,
                'error': result.get('error'),
                'code': 'quota_blocked',
                'organization': organization.slug,
                'quota': tenant_services.quota_status(organization),
            }, status=402)

        return JsonResponse({
            'success': False,
            'error': f'Could not post to the channel: {result.get("error")}',
            'post_id': post.pk,
        }, status=502)

    TenantAuditLog.record(
        organization, request.user, 'job_post.created',
        obj=post, job_post_id=job_post.pk if job_post else None,
    )

    quota = tenant_services.quota_status(organization)
    return JsonResponse({
        'success': True,
        'post_id': post.pk,
        'message_id': post.telegram_message_id,
        'job_post_id': job_post.pk if job_post else None,
        'organization': organization.slug,
        'organization_created': org_created,
        'quota': quota,
        'message': f'Posted "{title}" to the channel.',
    })


# ======================================================================
# Browse
# ======================================================================
def _scoped_posts(user, requested_slug=None):
    """
    Channel posts this employer may see.

    Their own posts always. Plus posts belonging to any workspace they are an
    active member of -- a company's applicants are the company's, not one
    individual's. Never another tenant's.
    """
    from django.db.models import Q

    queryset = ChannelPost.objects.select_related('job_post', 'organization')

    if requested_slug:
        organization = tenant_services.get_organization(user, requested_slug)
        return queryset.filter(organization=organization)

    org_ids = tenant_provisioning.visible_organization_ids(user)
    if org_ids:
        return queryset.filter(Q(employer=user) | Q(organization_id__in=org_ids))
    return queryset.filter(employer=user)


@login_required
def employer_my_posts(request: HttpRequest) -> JsonResponse:
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'error': 'Sign in first'}, status=401)
    if not _is_employer(request.user):
        return JsonResponse({'success': False, 'error': 'Employers only'}, status=403)

    try:
        posts = _scoped_posts(request.user, requested_slug=request.GET.get('organization_slug'))
    except PermissionDenied as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=403)

    posts = posts.order_by('-created_at')[:50]

    return JsonResponse({
        'success': True,
        'results': [{
            'id': p.pk,
            'title': p.title,
            'status': p.status,
            'organization': p.organization.slug if p.organization_id else None,
            'organization_name': p.organization.name if p.organization_id else None,
            'posted_by': p.employer.username if p.employer_id else None,
            'published_at': p.published_at.isoformat() if p.published_at else None,
            'telegram_message_id': p.telegram_message_id,
            'applicants': p.applications.count(),
            'publish_error': p.publish_error,
        } for p in posts],
    })


@login_required
def employer_applications(request: HttpRequest) -> JsonResponse:
    """
    Applicants across every post this employer owns, newest first.
    """
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'error': 'Sign in first'}, status=401)
    if not _is_employer(request.user):
        return JsonResponse({'success': False, 'error': 'Employers only'}, status=403)

    try:
        posts = _scoped_posts(request.user,
                             requested_slug=request.GET.get('organization_slug'))
    except PermissionDenied as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=403)

    post_id = request.GET.get('post_id')
    # Reuse the same scoping for the post filter so a caller cannot widen
    # access by passing someone else's post_id.
    queryset = (PostApplication.objects
                .filter(post__in=posts)
                .select_related('applicant', 'post'))

    if post_id:
        if not posts.filter(pk=post_id).exists():
            return JsonResponse({'success': False, 'error': 'Not found'}, status=404)
        queryset = queryset.filter(post_id=post_id)

    status_filter = request.GET.get('status')
    if status_filter:
        queryset = queryset.filter(status=status_filter)

    results = []
    for application in queryset[:100]:
        applicant = application.applicant
        seeker = getattr(applicant, 'job_seeker_profile', None)
        results.append({
            'id': application.pk,
            'post_id': application.post_id,
            'post_title': application.post.title,
            'applicant_id': applicant.pk,
            'name': applicant.get_full_name() or applicant.username,
            'title': getattr(seeker, 'title', '') or '',
            'skills': getattr(seeker, 'skills', []) or [],
            'location': getattr(seeker, 'city', '') or getattr(seeker, 'country', '') or '',
            'hourly_rate': str(getattr(seeker, 'hourly_rate', '') or ''),
            'is_verified': bool(getattr(seeker, 'is_verified', False)),
            'status': application.status,
            'status_label': application.get_status_display(),
            'admin_note': application.admin_note,
            'created_at': application.created_at.isoformat(),
        })

    return JsonResponse({'success': True, 'results': results})


@csrf_exempt
@login_required
def employer_update_application(request: HttpRequest, application_id: int) -> JsonResponse:
    """Shortlist, reject, or reset an applicant."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)
    if not _is_employer(request.user):
        return JsonResponse({'success': False, 'error': 'Employers only'}, status=403)

    try:
        visible_posts = _scoped_posts(request.user)
    except PermissionDenied as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=403)

    application = (PostApplication.objects
                   .filter(pk=application_id, post__in=visible_posts)
                   .select_related('applicant', 'post').first())
    if application is None:
        return JsonResponse({'success': False, 'error': 'Not found'}, status=404)

    data = _body(request)
    new_status = (data.get('status') or '').strip()
    allowed = {
        PostApplication.STATUS_SUBMITTED,
        PostApplication.STATUS_REVIEWING,
        PostApplication.STATUS_SHORTLISTED,
        PostApplication.STATUS_REJECTED,
    }
    if new_status not in allowed:
        return JsonResponse(
            {'success': False,
             'error': f'Status must be one of: {sorted(allowed)}'},
            status=400,
        )

    application.status = new_status
    note = (data.get('admin_note') or '').strip()
    if note:
        application.admin_note = note[:1000]
    application.save()

    if application.post.organization_id:
        TenantAuditLog.record(
            application.post.organization, request.user, 'application.updated',
            obj=application, status=new_status,
        )

    # Let the applicant know.
    from billing.services import resolve_chat_id, send_to_user

    chat_id = resolve_chat_id(application.applicant)
    if chat_id:
        icon = {
            PostApplication.STATUS_SHORTLISTED: '\U0001F3C1',
            PostApplication.STATUS_REJECTED: '\u274C',
        }.get(new_status, '\U0001F4E2')
        send_to_user(
            chat_id,
            f'{icon} *{application.post.title}*\n\n'
            f'Your application is now: *{application.get_status_display()}*.\n\n'
            + (f'Note from the employer: {application.admin_note}\n\n' if note else ''),
        )

    return JsonResponse({
        'success': True,
        'id': application.pk,
        'status': application.status,
        'status_label': application.get_status_display(),
    })


# ======================================================================
# Alert preferences (all three modes, user chooses)
# ======================================================================
@csrf_exempt
@login_required
def set_alert_preferences(request: HttpRequest) -> JsonResponse:
    """
    Let a subscriber pick how they hear about new posts.

    mode  : immediate | digest | matched
    hour  : local hour for the digest (0-23)
    muted : pause alerts
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)

    subscription = (
        Subscription.objects.filter(
            user=request.user, status=Subscription.STATUS_ACTIVE
        ).order_by('-created_at').first()
    )
    if subscription is None:
        return JsonResponse(
            {'success': False, 'error': 'You have no active subscription.'}, status=404
        )

    data = _body(request)
    mode = (data.get('mode') or '').strip()
    if mode and mode not in dict(Subscription.ALERT_MODE_CHOICES):
        return JsonResponse(
            {'success': False, 'error': f'Unknown mode: {mode}'}, status=400
        )

    changed = []
    if mode:
        subscription.alert_mode = mode
        changed.append('alert_mode')
    if 'hour' in data:
        try:
            hour = int(data['hour'])
        except (TypeError, ValueError):
            return JsonResponse({'success': False, 'error': 'Bad hour'}, status=400)
        if not 0 <= hour <= 23:
            return JsonResponse(
                {'success': False, 'error': 'Hour must be 0-23'}, status=400
            )
        subscription.digest_hour = hour
        changed.append('digest_hour')
    if 'muted' in data:
        subscription.alerts_muted = bool(data['muted'])
        changed.append('alerts_muted')

    if changed:
        subscription.save(update_fields=changed)

    return JsonResponse({
        'success': True,
        'alert_mode': subscription.alert_mode,
        'digest_hour': subscription.digest_hour,
        'alerts_muted': subscription.alerts_muted,
        'modes': [{'value': v, 'label': l}
                  for v, l in Subscription.ALERT_MODE_CHOICES],
    })


@login_required
def get_alert_preferences(request: HttpRequest) -> JsonResponse:
    subscription = (
        Subscription.objects.filter(
            user=request.user, status=Subscription.STATUS_ACTIVE
        ).order_by('-created_at').first()
    )
    if subscription is None:
        return JsonResponse({
            'success': True,
            'subscribed': False,
            'modes': [{'value': v, 'label': l}
                      for v, l in Subscription.ALERT_MODE_CHOICES],
        })

    return JsonResponse({
        'success': True,
        'subscribed': True,
        'alert_mode': subscription.alert_mode,
        'digest_hour': subscription.digest_hour,
        'alerts_muted': subscription.alerts_muted,
        'expires_at': subscription.expires_at.isoformat() if subscription.expires_at else None,
        'modes': [{'value': v, 'label': l}
                  for v, l in Subscription.ALERT_MODE_CHOICES],
    })
