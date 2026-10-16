"""
Tenant API used by the web app and the mini app.

Every read is membership-scoped on the server. The client is never trusted
to say which organisation it wants; it passes a slug and the server checks.
"""
from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from . import services
from .models import (
    Invitation,
    Membership,
    Organization,
    TenantAuditLog,
    TenantPlan,
)

ORG_TYPES = {c[0] for c in Organization.TYPE_CHOICES}
MEMBER_ROLES = {c[0] for c in Membership.ROLE_CHOICES}


def _body(request: HttpRequest) -> dict:
    try:
        return json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        return {}


def _err(message, status=400):
    return JsonResponse({'success': False, 'error': message}, status=status)


# ======================================================================
# Plans (public: needed to show pricing before signing up)
# ======================================================================
def list_plans(request: HttpRequest) -> JsonResponse:
    org_type = request.GET.get('type', '')
    plans = TenantPlan.objects.filter(is_active=True)
    results = []
    for plan in plans:
        if org_type and not plan.applies_to_type(org_type):
            continue
        results.append({
            'slug': plan.slug,
            'name': plan.name,
            'description': plan.description,
            'price': str(plan.price),
            'price_per_month': str(plan.price_per_month),
            'billing_cycle': plan.billing_cycle,
            'job_post_limit': plan.job_post_limit,
            'seat_limit': plan.seat_limit,
            'can_use_own_channel': plan.can_use_own_channel,
            'can_export_data': plan.can_export_data,
        })
    return JsonResponse({'success': True, 'results': results})


# ======================================================================
# Create / list organisations
# ======================================================================
@csrf_exempt
@login_required
def create_organization(request: HttpRequest) -> JsonResponse:
    if request.method != 'POST':
        return _err('POST required', 405)

    data = _body(request)
    name = (data.get('name') or '').strip()
    org_type = (data.get('organization_type') or '').strip()
    if not name:
        return _err('Organization name is required')
    if org_type not in ORG_TYPES:
        return _err(f'organization_type must be one of {sorted(ORG_TYPES)}')

    existing = Organization.objects.filter(
        name__iexact=name, status=Organization.STATUS_ACTIVE
    ).first()
    if existing:
        return _err(f'An organization called "{name}" already exists.', 409)

    with transaction.atomic():
        organization = Organization.objects.create(
            name=name,
            organization_type=org_type,
            legal_name=(data.get('legal_name') or '').strip(),
            description=(data.get('description') or '').strip(),
            website=(data.get('website') or '').strip(),
            email=(data.get('email') or request.user.email or '').strip(),
            phone=(data.get('phone') or '').strip(),
            address=(data.get('address') or '').strip(),
            city=(data.get('city') or '').strip(),
            country=(data.get('country') or 'Ethiopia').strip(),
            created_by=request.user,
            status=Organization.STATUS_ACTIVE,
        )
        Membership.objects.create(
            organization=organization,
            user=request.user,
            role=Membership.ROLE_OWNER,
            is_active=True,
        )
        TenantAuditLog.record(organization, request.user, 'organization.created',
                              obj=organization, request=request)

    return JsonResponse({
        'success': True,
        'organization': {
            'id': organization.pk,
            'name': organization.name,
            'slug': organization.slug,
            'type': organization.organization_type,
            'status': organization.status,
            'your_role': Membership.ROLE_OWNER,
        },
    }, status=201)


@login_required
def list_organizations(request: HttpRequest) -> JsonResponse:
    orgs = services.organizations_for(request.user)
    return JsonResponse({
        'success': True,
        'results': [{
            'id': o.pk,
            'name': o.name,
            'slug': o.slug,
            'type': o.organization_type,
            'type_label': o.get_organization_type_display(),
            'status': o.status,
            'is_verified': o.is_verified,
            'your_role': o.role_for(request.user),
            'logo': o.logo.url if o.logo else '',
        } for o in orgs],
    })


@login_required
def organization_detail(request: HttpRequest, slug: str) -> JsonResponse:
    try:
        organization = services.get_organization(request.user, slug)
    except PermissionDenied as exc:
        return _err(str(exc), 403)

    quota = services.quota_status(organization)
    may_publish, publish_reason = services.can_publish_job(organization)

    return JsonResponse({
        'success': True,
        'organization': {
            'id': organization.pk,
            'name': organization.name,
            'slug': organization.slug,
            'type': organization.organization_type,
            'type_label': organization.get_organization_type_display(),
            'status': organization.status,
            'description': organization.description,
            'website': organization.website,
            'city': organization.city,
            'is_verified': organization.is_verified,
            'logo': organization.logo.url if organization.logo else '',
            'member_count': organization.memberships.filter(is_active=True).count(),
        },
        'your_role': organization.role_for(request.user),
        'quota': quota,
        'can_publish': may_publish,
        'cannot_publish_reason': publish_reason,
    })


# ======================================================================
# Members
# ======================================================================
@login_required
def list_members(request: HttpRequest, slug: str) -> JsonResponse:
    try:
        organization = services.get_organization(request.user, slug)
    except PermissionDenied as exc:
        return _err(str(exc), 403)

    memberships = organization.memberships.select_related('user').order_by(
        'role', 'user__username'
    )
    return JsonResponse({
        'success': True,
        'results': [{
            'user_id': m.user_id,
            'username': m.user.username,
            'email': m.user.email,
            'full_name': (m.user.get_full_name() or m.user.username),
            'role': m.role,
            'role_label': m.get_role_display(),
            'is_active': m.is_active,
            'job_title': m.job_title,
            'joined_at': m.joined_at.isoformat() if m.joined_at else None,
        } for m in memberships],
    })


@csrf_exempt
@login_required
def invite_member(request: HttpRequest, slug: str) -> JsonResponse:
    if request.method != 'POST':
        return _err('POST required', 405)
    try:
        organization = services.get_organization(request.user, slug)
    except PermissionDenied as exc:
        return _err(str(exc), 403)

    if not services.can_manage(request.user, organization):
        return _err('Only an owner or admin can invite people.', 403)

    data = _body(request)
    email = (data.get('email') or '').strip().lower()
    role = (data.get('role') or Membership.ROLE_VIEWER).strip()
    if not email or '@' not in email:
        return _err('A valid email is required')
    if role not in MEMBER_ROLES:
        return _err(f'Unknown role {role}')
    if role == Membership.ROLE_OWNER:
        return _err('Ownership is transferred separately, not by invitation.')

    quota = services.quota_status(organization)
    if quota['seat_limit'] and quota['seats_used'] >= quota['seat_limit']:
        return _err(
            f'Seat limit reached ({quota["seats_used"]}/{quota["seat_limit"]}). '
            f'Upgrade the plan to invite more people.', 402,
        )

    invitation, created = Invitation.objects.get_or_create(
        organization=organization,
        email=email,
        accepted_at__isnull=True,
        defaults={'role': role, 'invited_by': request.user},
    )
    TenantAuditLog.record(organization, request.user, 'member.invited',
                          obj=organization, request=request, email=email, role=role)

    return JsonResponse({
        'success': True,
        'invitation_id': invitation.pk,
        'email': invitation.email,
        'role': invitation.role,
        'created': created,
        'token': str(invitation.token),
        'expires_at': invitation.expires_at.isoformat(),
    }, status=201 if created else 200)


@csrf_exempt
@login_required
def change_member_role(request: HttpRequest, slug: str, user_id: int) -> JsonResponse:
    if request.method != 'POST':
        return _err('POST required', 405)
    try:
        organization = services.get_organization(request.user, slug)
    except PermissionDenied as exc:
        return _err(str(exc), 403)
    if not services.can_manage(request.user, organization):
        return _err('Only an owner or admin can change roles.', 403)

    membership = organization.memberships.filter(user_id=user_id).select_related(
        'user').first()
    if membership is None:
        return _err('That person is not a member.', 404)

    data = _body(request)
    role = (data.get('role') or '').strip()
    if role not in MEMBER_ROLES:
        return _err(f'Unknown role {role}')

    owners = organization.memberships.filter(role=Membership.ROLE_OWNER,
                                            is_active=True)
    if membership.role == Membership.ROLE_OWNER and role != Membership.ROLE_OWNER:
        if owners.count() <= 1:
            return _err(
                'An organization must keep at least one owner. '
                'Transfer ownership first.', 409,
            )

    membership.role = role
    membership.save(update_fields=['role'])
    TenantAuditLog.record(organization, request.user, 'member.role_changed',
                          obj=organization, request=request,
                          user_id=user_id, role=role)
    return JsonResponse({'success': True, 'user_id': user_id, 'role': role})


@csrf_exempt
@login_required
def remove_member(request: HttpRequest, slug: str, user_id: int) -> JsonResponse:
    if request.method != 'POST':
        return _err('POST required', 405)
    try:
        organization = services.get_organization(request.user, slug)
    except PermissionDenied as exc:
        return _err(str(exc), 403)
    if not services.can_manage(request.user, organization):
        return _err('Only an owner or admin can remove people.', 403)

    membership = organization.memberships.filter(user_id=user_id).first()
    if membership is None:
        return _err('That person is not a member.', 404)
    if membership.user_id == request.user.id:
        return _err('You cannot remove yourself. Transfer ownership first.', 409)
    if membership.role == Membership.ROLE_OWNER:
        owners = organization.memberships.filter(role=Membership.ROLE_OWNER,
                                                is_active=True)
        if owners.count() <= 1:
            return _err('An organization must keep at least one owner.', 409)

    username = membership.user.username
    membership.is_active = False
    membership.save(update_fields=['is_active'])
    TenantAuditLog.record(organization, request.user, 'member.removed',
                          obj=organization, request=request,
                          user_id=user_id, username=username)
    return JsonResponse({'success': True, 'removed': username})


# ======================================================================
# Invitations
# ======================================================================
@login_required
def my_invitations(request: HttpRequest) -> JsonResponse:
    """
    Open invitations addressed to the signed-in user's email.
    """
    email = (request.user.email or '').strip().lower()
    if not email:
        return JsonResponse({'success': True, 'results': []})

    invitations = (Invitation.objects
                   .filter(email__iexact=email, accepted_at__isnull=True)
                   .select_related('organization')
                   .order_by('-created_at'))

    return JsonResponse({
        'success': True,
        'results': [{
            'token': str(i.token),
            'organization': i.organization.slug,
            'organization_name': i.organization.name,
            'role': i.role,
            'role_label': i.get_role_display(),
            'expires_at': i.expires_at.isoformat(),
            'is_expired': not i.is_open,
        } for i in invitations],
    })


@csrf_exempt
@login_required
def accept_invitation(request: HttpRequest, token: str) -> JsonResponse:
    """
    Redeem an invitation token and join the workspace.

    The email is checked against the signed-in account so a forwarded link
    cannot be used to slip into someone else's company.
    """
    invitation = Invitation.objects.filter(token=token).select_related(
        'organization').first()
    if invitation is None:
        return _err('That invitation link is not valid.', 404)
    if invitation.accepted_at is not None:
        return _err('That invitation has already been used.', 409)
    if not invitation.is_open:
        return _err('That invitation has expired. Ask for a new one.', 409)

    account_email = (request.user.email or '').strip().lower()
    if account_email != invitation.email.lower():
        return _err(
            f'This invitation was sent to {invitation.email}. '
            f'Sign in with that address to accept it.', 403,
        )

    with transaction.atomic():
        membership, created = Membership.objects.get_or_create(
            organization=invitation.organization,
            user=request.user,
            defaults={
                'role': invitation.role,
                'is_active': True,
                'invited_by': invitation.invited_by,
                'joined_at': timezone.now(),
            },
        )
        if not created and not membership.is_active:
            membership.is_active = True
            membership.role = invitation.role
            membership.save(update_fields=['is_active', 'role'])

        invitation.accepted_at = timezone.now()
        invitation.accepted_by = request.user
        invitation.save(update_fields=['accepted_at', 'accepted_by'])

        TenantAuditLog.record(
            invitation.organization, request.user, 'member.joined',
            obj=invitation.organization, request=request,
            role=invitation.role, via='invitation',
        )

    return JsonResponse({
        'success': True,
        'organization': invitation.organization.slug,
        'organization_name': invitation.organization.name,
        'role': membership.role,
        'role_label': membership.get_role_display(),
    })


# ======================================================================
# Billing
# ======================================================================
@login_required
def organization_quota(request: HttpRequest, slug: str) -> JsonResponse:
    try:
        organization = services.get_organization(request.user, slug)
    except PermissionDenied as exc:
        return _err(str(exc), 403)
    may_publish, reason = services.can_publish_job(organization)
    quota = services.quota_status(organization)
    quota['can_publish'] = may_publish
    quota['cannot_publish_reason'] = reason
    quota['success'] = True
    return JsonResponse(quota)


# ======================================================================
# Dashboard
# ======================================================================
@login_required
def organization_dashboard(request: HttpRequest, slug: str) -> JsonResponse:
    """Counts the employer UI needs, all membership-scoped."""
    try:
        organization = services.get_organization(request.user, slug)
    except PermissionDenied as exc:
        return _err(str(exc), 403)

    from jobs.models import JobApplication, JobPost

    posts = JobPost.objects.filter(organization=organization)
    channel_posts = organization.channel_posts.all()
    may_publish, reason = services.can_publish_job(organization)

    return JsonResponse({
        'success': True,
        'organization': {'id': organization.pk, 'name': organization.name,
                         'slug': organization.slug},
        'stats': {
            'job_posts': posts.count(),
            'open_job_posts': posts.filter(status='open').count(),
            'channel_posts': channel_posts.count(),
            'applicants': JobApplication.objects.filter(
                job__organization=organization).count(),
            'members': organization.memberships.filter(is_active=True).count(),
        },
        'quota': services.quota_status(organization),
        'can_publish': may_publish,
        'cannot_publish_reason': reason,
    })
