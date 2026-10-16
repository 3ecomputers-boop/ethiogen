"""
Server-rendered tenant pages.

Two audiences:

* **Workspace** (`/workspaces/...`) -- what a company's own staff see. Every
  read goes through ``services.get_organization`` or ``services.scope``, so a
  user who is not an active member of an organisation gets a 404 rather than
  a 403: telling a stranger "this exists but you cannot see it" is a small
  but free information leak.
* **Console** (`/console/...`) -- what the platform operator sees, across all
  tenants. Superuser only.

Nothing here duplicates the quota or capability logic -- those live in
``services`` and are called, not reimplemented.
"""
from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q, Sum
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import provisioning, services
from .models import (
    Invitation,
    Membership,
    Organization,
    TenantAuditLog,
    TenantPlan,
    TenantSubscription,
)

console_required = user_passes_test(
    lambda u: u.is_authenticated and u.is_superuser,
    login_url='/admin/login/',
)


# ======================================================================
# Helpers
# ======================================================================
def _organization_or_404(user, slug) -> Organization:
    """
    Fetch an organisation the user belongs to.

    Non-members and unknown slugs both produce a 404, so the page cannot be
    used to probe which tenant slugs exist.
    """
    try:
        return services.get_organization(user, slug)
    except PermissionDenied:
        raise Http404('No such workspace.')


def _require(user, organization, capability) -> None:
    if not services.can(user, organization, capability):
        raise Http404('No such workspace.')


def _quota_progress(used: int, limit: int) -> dict:
    """Shape a job-post counter for the template.

    `remaining` is computed here because Django templates cannot do
    arithmetic.
    """
    if not limit:
        return {'used': used, 'limit': limit, 'pct': 0,
                'unlimited': True, 'remaining': None}
    pct = min(100, round(used / limit * 100)) if limit else 0
    return {'used': used, 'limit': limit, 'pct': pct,
            'unlimited': False, 'remaining': max(0, limit - used)}


def _monthly_revenue() -> Decimal:
    """MRR: annual plans counted at 1/12 of their price."""
    total = Decimal('0')
    for subscription in (TenantSubscription.objects
                         .select_related('plan')
                         .exclude(status__in=[TenantSubscription.STATUS_CANCELLED,
                                              TenantSubscription.STATUS_EXPIRED])):
        if not subscription.is_current:
            continue
        total += subscription.plan.price_per_month
    return total


# ======================================================================
# Employer workspace
# ======================================================================
@login_required
def workspace_list(request):
    organizations = services.organizations_for(request.user).prefetch_related(
        'subscriptions__plan')

    cards = []
    for organization in organizations:
        quota = services.quota_status(organization)
        cards.append({
            'organization': organization,
            'role': organization.role_for(request.user),
            'quota': quota,
            'progress': _quota_progress(quota['job_posts_used'],
                                        quota['job_post_limit']),
        })

    return render(request, 'tenants/workspace_list.html', {
        'cards': cards,
        'open_invitations': Invitation.objects.filter(
            email__iexact=(request.user.email or ''),
            accepted_at__isnull=True,
        ).select_related('organization'),
    })


@login_required
def workspace_detail(request, slug):
    organization = _organization_or_404(request.user, slug)
    _require(request.user, organization, 'view')

    from billing.models import ChannelPost
    from jobs.models import JobApplication, JobPost

    quota = services.quota_status(organization)
    may_publish, publish_reason = services.can_publish_job(organization)

    job_posts = JobPost.objects.filter(organization=organization)
    channel_posts = organization.channel_posts.all()

    context = {
        'organization': organization,
        'role': organization.role_for(request.user),
        'quota': quota,
        'progress': _quota_progress(quota['job_posts_used'], quota['job_post_limit']),
        'can_manage': services.can_manage(request.user, organization),
        'can_publish': may_publish,
        'publish_reason': publish_reason,
        'stats': {
            'job_posts': job_posts.count(),
            'open_job_posts': job_posts.filter(status='open').count(),
            'channel_posts': channel_posts.count(),
            'applicants': JobApplication.objects.filter(
                job__organization=organization).count(),
            'members': organization.memberships.filter(is_active=True).count(),
        },
        'recent_posts': channel_posts.order_by('-created_at')[:5],
        'recent_activity': (TenantAuditLog.objects
                            .filter(organization=organization)
                            .select_related('user')[:8]),
        'can_create_org': not organization.has_member(request.user),
    }
    return render(request, 'tenants/workspace_detail.html', context)


@login_required
def workspace_members(request, slug):
    organization = _organization_or_404(request.user, slug)
    _require(request.user, organization, 'view')
    can_manage = services.can_manage(request.user, organization)

    memberships = (organization.memberships
                   .select_related('user')
                   .order_by('role', 'user__username'))

    return render(request, 'tenants/workspace_members.html', {
        'organization': organization,
        'role': organization.role_for(request.user),
        'memberships': memberships,
        'can_manage': can_manage,
        'role_choices': Membership.ROLE_CHOICES,
        'invitations': (organization.invitations
                        .filter(accepted_at__isnull=True)
                        .order_by('-created_at')) if can_manage else [],
        'quota': services.quota_status(organization),
    })


@login_required
@require_POST
def workspace_invite(request, slug):
    organization = _organization_or_404(request.user, slug)
    if not services.can_manage(request.user, organization):
        messages.error(request, 'Only an owner or admin can invite people.')
        return redirect('tenants:workspace_members', slug=organization.slug)

    email = (request.POST.get('email') or '').strip().lower()
    role = (request.POST.get('role') or Membership.ROLE_VIEWER).strip()

    if not email or '@' not in email:
        messages.error(request, 'Enter a valid email address.')
        return redirect('tenants:workspace_members', slug=organization.slug)
    if role not in dict(Membership.ROLE_CHOICES):
        messages.error(request, 'Unknown role.')
        return redirect('tenants:workspace_members', slug=organization.slug)
    if role == Membership.ROLE_OWNER:
        messages.error(request, 'Ownership is transferred separately.')
        return redirect('tenants:workspace_members', slug=organization.slug)

    quota = services.quota_status(organization)
    if quota['seat_limit'] and quota['seats_used'] >= quota['seat_limit']:
        messages.error(
            request,
            f'Seat limit reached ({quota["seats_used"]}/{quota["seat_limit"]}). '
            f'Upgrade the plan to invite more people.',
        )
        return redirect('tenants:workspace_members', slug=organization.slug)

    invitation, created = Invitation.objects.get_or_create(
        organization=organization,
        email=email,
        accepted_at__isnull=True,
        defaults={'role': role, 'invited_by': request.user},
    )
    TenantAuditLog.record(organization, request.user, 'member.invited',
                          obj=organization, request=request,
                          email=email, role=role)
    if created:
        messages.success(request, f'Invitation created for {email}.')
    else:
        messages.info(request, f'An open invitation for {email} already existed.')

    return redirect('tenants:workspace_members', slug=organization.slug)


@login_required
@require_POST
def workspace_change_role(request, slug, user_id):
    organization = _organization_or_404(request.user, slug)
    if not services.can_manage(request.user, organization):
        messages.error(request, 'Only an owner or admin can change roles.')
        return redirect('tenants:workspace_members', slug=organization.slug)

    membership = get_object_or_404(Membership, organization=organization,
                                   user_id=user_id)
    role = (request.POST.get('role') or '').strip()

    if role not in dict(Membership.ROLE_CHOICES):
        messages.error(request, 'Unknown role.')
    elif (membership.role == Membership.ROLE_OWNER and role != Membership.ROLE_OWNER
          and organization.memberships.filter(role=Membership.ROLE_OWNER,
                                              is_active=True).count() <= 1):
        messages.error(request, 'An organization must keep at least one owner. '
                                'Promote someone else first.')
    else:
        membership.role = role
        membership.save(update_fields=['role'])
        TenantAuditLog.record(organization, request.user, 'member.role_changed',
                              obj=organization, request=request,
                              user_id=user_id, role=role)
        messages.success(request, f'Role updated to {membership.get_role_display()}.')

    return redirect('tenants:workspace_members', slug=organization.slug)


@login_required
@require_POST
def workspace_remove_member(request, slug, user_id):
    organization = _organization_or_404(request.user, slug)
    if not services.can_manage(request.user, organization):
        messages.error(request, 'Only an owner or admin can remove people.')
        return redirect('tenants:workspace_members', slug=organization.slug)

    membership = get_object_or_404(Membership, organization=organization,
                                   user_id=user_id)

    if membership.user_id == request.user.id:
        messages.error(request, 'You cannot remove yourself.')
    elif (membership.role == Membership.ROLE_OWNER
          and organization.memberships.filter(role=Membership.ROLE_OWNER,
                                              is_active=True).count() <= 1):
        messages.error(request, 'An organization must keep at least one owner.')
    else:
        username = membership.user.username
        membership.is_active = False
        membership.save(update_fields=['is_active'])
        TenantAuditLog.record(organization, request.user, 'member.removed',
                              obj=organization, request=request,
                              user_id=user_id, username=username)
        messages.success(request, f'{username} removed from the workspace.')

    return redirect('tenants:workspace_members', slug=organization.slug)


@login_required
def workspace_billing(request, slug):
    organization = _organization_or_404(request.user, slug)
    _require(request.user, organization, 'view')

    subscription = services.current_subscription(organization)
    organization_type = organization.organization_type
    plans = [p for p in TenantPlan.objects.filter(is_active=True)
             if p.applies_to_type(organization_type)]

    return render(request, 'tenants/workspace_billing.html', {
        'organization': organization,
        'role': organization.role_for(request.user),
        'subscription': subscription,
        'quota': services.quota_status(organization),
        'progress': _quota_progress(services.quota_status(organization)['job_posts_used'],
                                    services.quota_status(organization)['job_post_limit']),
        'plans': plans,
        'can_manage_billing': services.can(request.user, organization,
                                            'manage_billing'),
    })


@login_required
def workspace_jobs(request, slug):
    organization = _organization_or_404(request.user, slug)
    _require(request.user, organization, 'view')

    from billing.models import ChannelPost
    from jobs.models import JobApplication, JobPost

    job_posts = (JobPost.objects.filter(organization=organization)
                 .annotate(applicant_total=Count('applications'))
                 .order_by('-created_at')[:100])
    channel_posts = organization.channel_posts.all().order_by('-created_at')[:100]

    return render(request, 'tenants/workspace_jobs.html', {
        'organization': organization,
        'role': organization.role_for(request.user),
        'job_posts': job_posts,
        'channel_posts': channel_posts,
        'quota': services.quota_status(organization),
        'can_publish': services.can_publish_job(organization)[0],
    })


@login_required
def workspace_create(request):
    """Create a workspace when the user has none."""
    if request.method == 'POST':
        name = (request.POST.get('name') or '').strip()
        organization_type = (request.POST.get('organization_type')
                             or Organization.TYPE_CONSTRUCTION_COMPANY)
        if not name:
            messages.error(request, 'Organization name is required.')
        elif organization_type not in dict(Organization.TYPE_CHOICES):
            messages.error(request, 'Unknown organization type.')
        elif Organization.objects.filter(name__iexact=name,
                                         status=Organization.STATUS_ACTIVE).exists():
            messages.error(request, f'An organization called "{name}" already exists.')
        else:
            organization = Organization.objects.create(
                name=name,
                organization_type=organization_type,
                status=Organization.STATUS_ACTIVE,
                email=request.user.email or '',
                city=(request.POST.get('city') or '')[:120],
                website=(request.POST.get('website') or '')[:200],
                description=(request.POST.get('description') or '')[:2000],
                created_by=request.user,
            )
            Membership.objects.create(
                organization=organization, user=request.user,
                role=Membership.ROLE_OWNER, is_active=True)

            plan = provisioning.default_trial_plan()
            if plan is not None:
                TenantSubscription.objects.create(
                    organization=organization, plan=plan,
                    status=TenantSubscription.STATUS_TRIALING,
                    starts_at=timezone.now(),
                    ends_at=timezone.now() + timedelta(days=provisioning.TRIAL_DAYS),
                    auto_renew=False,
                )
            TenantAuditLog.record(organization, request.user, 'organization.created',
                                  obj=organization, request=request)
            messages.success(request, f'{organization.name} created.')
            return redirect('tenants:workspace_detail', slug=organization.slug)

    return render(request, 'tenants/workspace_create.html', {
        'type_choices': Organization.TYPE_CHOICES,
        'default_plan': provisioning.default_trial_plan(),
    })


# ======================================================================
# Invitations
# ======================================================================
@login_required
def accept_invitation(request, token):
    invitation = Invitation.objects.filter(token=token).select_related(
        'organization').first()

    if invitation is None:
        messages.error(request, 'That invitation link is not valid.')
        return redirect('tenants:workspace_list')
    if invitation.accepted_at is not None:
        messages.info(request, 'That invitation has already been used.')
        return redirect('tenants:workspace_detail',
                        slug=invitation.organization.slug)
    if not invitation.is_open:
        messages.error(request, 'That invitation has expired. Ask for a new one.')
        return redirect('tenants:workspace_list')

    account_email = (request.user.email or '').strip().lower()
    if account_email != invitation.email.lower():
        messages.error(
            request,
            f'This invitation was sent to {invitation.email}. '
            f'Sign in with that address to accept it.',
        )
        return redirect('tenants:workspace_list')

    if request.method == 'POST':
        membership, created = Membership.objects.get_or_create(
            organization=invitation.organization,
            user=request.user,
            defaults={'role': invitation.role, 'is_active': True,
                      'invited_by': invitation.invited_by,
                      'joined_at': timezone.now()},
        )
        if not created and not membership.is_active:
            membership.is_active = True
            membership.role = invitation.role
            membership.save(update_fields=['is_active', 'role'])

        invitation.accepted_at = timezone.now()
        invitation.accepted_by = request.user
        invitation.save(update_fields=['accepted_at', 'accepted_by'])
        TenantAuditLog.record(invitation.organization, request.user,
                              'member.joined', obj=invitation.organization,
                              request=request, role=invitation.role,
                              via='invitation')
        messages.success(request,
                         f'You joined {invitation.organization.name}.')
        return redirect('tenants:workspace_detail',
                        slug=invitation.organization.slug)

    return render(request, 'tenants/accept_invitation.html', {
        'invitation': invitation,
        'organization': invitation.organization,
    })


# ======================================================================
# Operator console (superuser only)
# ======================================================================
@console_required
def console_dashboard(request):
    organizations = Organization.objects.all()
    active = organizations.filter(status=Organization.STATUS_ACTIVE)
    current_subs = [s for s in TenantSubscription.objects
                    .select_related('plan', 'organization')
                    if s.is_current]

    expiring_soon = [s for s in current_subs
                     if s.ends_at and s.ends_at <= timezone.now() + timedelta(days=14)]

    by_type = list(
        organizations.values('organization_type')
        .annotate(n=Count('id'))
        .order_by('-n')
    )
    by_status = list(
        organizations.values('status').annotate(n=Count('id')).order_by('-n'))

    return render(request, 'tenants/console/dashboard.html', {
        'totals': {
            'organizations': organizations.count(),
            'active': active.count(),
            'verified': organizations.filter(is_verified=True).count(),
            'members': Membership.objects.filter(is_active=True).count(),
            'paying': len(current_subs),
            'trialing': len([s for s in current_subs
                             if s.status == TenantSubscription.STATUS_TRIALING]),
            'mrr': _monthly_revenue(),
            'job_posts': organizations.aggregate(
                n=Sum('job_posts__id'))['n'] or 0,
        },
        'by_type': by_type,
        'by_status': by_status,
        'recent_orgs': organizations.order_by('-created_at')[:10],
        'expiring_soon': sorted(expiring_soon,
                                key=lambda s: s.ends_at)[:10],
        'recent_audit': (TenantAuditLog.objects
                         .select_related('organization', 'user')
                         .order_by('-created_at')[:15]),
    })


@console_required
def console_organizations(request):
    organizations = Organization.objects.annotate(
        member_total=Count('memberships', filter=Q(memberships__is_active=True),
                           distinct=True),
    ).select_related('created_by')

    q = (request.GET.get('q') or '').strip()
    status = (request.GET.get('status') or '').strip()
    org_type = (request.GET.get('type') or '').strip()
    plan = (request.GET.get('plan') or '').strip()

    if q:
        organizations = organizations.filter(
            Q(name__icontains=q) | Q(slug__icontains=q) | Q(email__icontains=q)
            | Q(city__icontains=q) | Q(legal_name__icontains=q))
    if status:
        organizations = organizations.filter(status=status)
    if org_type:
        organizations = organizations.filter(organization_type=org_type)
    if plan:
        organizations = organizations.filter(
            subscriptions__plan__slug=plan).distinct()

    rows = []
    for organization in organizations.order_by('-created_at'):
        subscription = services.current_subscription(organization)
        rows.append({
            'organization': organization,
            'quota': services.quota_status(organization),
            'subscription': subscription,
            'role_count': organization.member_total,
        })

    return render(request, 'tenants/console/organizations.html', {
        'rows': rows,
        'status_choices': Organization.STATUS_CHOICES,
        'type_choices': Organization.TYPE_CHOICES,
        'plans': TenantPlan.objects.all(),
        'filters': {'q': q, 'status': status, 'type': org_type, 'plan': plan},
    })


@console_required
def console_organization_detail(request, pk):
    organization = get_object_or_404(Organization, pk=pk)
    subscription = services.current_subscription(organization)

    return render(request, 'tenants/console/organization_detail.html', {
        'organization': organization,
        'quota': services.quota_status(organization),
        'memberships': (organization.memberships.select_related('user')
                        .order_by('role')),
        'subscriptions': organization.subscriptions.select_related('plan'),
        'invitations': organization.invitations.order_by('-created_at')[:20],
        'audit': (TenantAuditLog.objects.filter(organization=organization)
                  .select_related('user')[:40]),
        'admin_url': f'/admin/tenants/organization/{organization.pk}/change/',
    })


@console_required
def console_plans(request):
    plans = TenantPlan.objects.annotate(
        subscriber_total=Count('subscriptions', distinct=True))
    return render(request, 'tenants/console/plans.html', {
        'plans': plans,
        'admin_url': '/admin/tenants/tenantplan/',
    })