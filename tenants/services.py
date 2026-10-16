"""
Tenant access rules.

Everything that reads or writes organisation data should go through here,
so a missing check is a visible omission rather than a silent data leak.
"""
from __future__ import annotations

from django.core.exceptions import PermissionDenied

from .models import Membership, Organization, TenantSubscription


# ======================================================================
# Visibility
# ======================================================================
def organizations_for(user):
    """Every organisation the user may see, as a QuerySet."""
    return Organization.objects.for_user(user)


def get_organization(user, slug_or_pk) -> Organization:
    """
    Fetch an organisation the user is allowed to see.

    Raises PermissionDenied rather than returning 404-with-no-body, so
    permission problems are debuggable.
    """
    try:
        if isinstance(slug_or_pk, int) or str(slug_or_pk).isdigit():
            organization = Organization.objects.filter(pk=int(slug_or_pk)).first()
        else:
            organization = Organization.objects.filter(slug=slug_or_pk).first()
    except (ValueError, TypeError):
        organization = None

    if organization is None:
        raise PermissionDenied('Organization not found.')
    if not organization.has_member(user):
        raise PermissionDenied('You do not have access to this organization.')
    return organization


# ======================================================================
# Capabilities
# ======================================================================
def role_in(user, organization) -> str | None:
    return organization.role_for(user)


def can(user, organization, capability: str) -> bool:
    """May `user` do `capability` inside `organization`?"""
    if user is None or not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'is_superuser', False):
        return True
    role = role_in(user, organization)
    if not role:
        return False
    return capability in Membership.CAPABILITIES.get(role, set())


def can_manage(user, organization) -> bool:
    return can(user, organization, 'manage_members')


def can_publish(user, organization) -> bool:
    return can(user, organization, 'publish')


def can_view(user, organization) -> bool:
    return can(user, organization, 'view')


def require(user, organization, capability: str) -> None:
    if not can(user, organization, capability):
        raise PermissionDenied(
            f'Your role ({role_in(user, organization) or "none"}) cannot {capability}.'
        )


# ======================================================================
# Scoped querysets
# ======================================================================
def scope(queryset, user, field: str = 'organization'):
    """
    Restrict a queryset to rows the user may see.

    Superusers see everything. Everyone else sees only rows belonging to an
    organisation they actively belong to.
    """
    if user is None or not getattr(user, 'is_authenticated', False):
        return queryset.none()
    if getattr(user, 'is_superuser', False):
        return queryset

    org_ids = (
        Membership.objects
        .filter(user=user, is_active=True)
        .values_list('organization_id', flat=True)
    )
    if not org_ids:
        return queryset.none()
    return queryset.filter(**{f'{field}_id__in': org_ids})


# ======================================================================
# Quotas
# ======================================================================
def current_subscription(organization):
    """The organisation's live subscription, or None."""
    return (
        TenantSubscription.objects
        .filter(organization=organization)
        .exclude(status__in=[TenantSubscription.STATUS_CANCELLED,
                             TenantSubscription.STATUS_EXPIRED])
        .order_by('-ends_at', '-created_at')
        .first()
    )


def quota_status(organization) -> dict:
    """
    Report plan limits and current usage. Used by the API and the admin so
    the numbers shown come from one place.
    """
    subscription = current_subscription(organization)
    if subscription is None:
        return {
            'has_plan': False,
            'plan': None,
            'job_post_limit': 0,
            'job_posts_used': 0,
            'job_posts_remaining': 0,
            'seat_limit': 0,
            'seats_used': Membership.objects.filter(
                organization=organization, is_active=True).count(),
            'expires_at': None,
        }

    limit = subscription.plan.job_post_limit
    used = subscription.job_posts_used
    return {
        'has_plan': True,
        'is_current': subscription.is_current,
        'plan': subscription.plan.name,
        'plan_slug': subscription.plan.slug,
        'status': subscription.status,
        'job_post_limit': limit,
        'job_posts_used': used,
        'job_posts_remaining': (limit - used) if limit else -1,  # -1 = unlimited
        'seat_limit': subscription.plan.seat_limit,
        'seats_used': Membership.objects.filter(
            organization=organization, is_active=True).count(),
        'can_use_own_channel': subscription.plan.can_use_own_channel,
        'expires_at': subscription.ends_at,
        'days_remaining': subscription.days_remaining,
    }


def can_publish_job(organization) -> tuple:
    """
    May this organisation post another job right now?

    Returns (allowed: bool, reason: str).
    """
    if organization.status != Organization.STATUS_ACTIVE:
        return False, 'This organization is not active.'

    subscription = current_subscription(organization)
    if subscription is None:
        return False, 'No active subscription. Choose a plan to post jobs.'
    if not subscription.is_current:
        return False, 'Your subscription has expired. Renew to post jobs.'

    limit = subscription.plan.job_post_limit
    if limit and subscription.job_posts_used >= limit:
        return False, (
            f'Job post limit reached ({subscription.job_posts_used}/{limit}). '
            f'Upgrade your plan or wait for the next period.'
        )
    return True, ''


def consume_job_post(organization) -> bool:
    """Increment the used counter after a successful publish. Returns True."""
    subscription = current_subscription(organization)
    if subscription is None:
        return False
    TenantSubscription.objects.filter(pk=subscription.pk).update(
        job_posts_used=subscription.job_posts_used + 1
    )
    return True
