"""
Workspace provisioning.

Turning an employer account into a tenant.

An employer signs up as a person: a User plus a ClientProfile. The SaaS
needs a workspace behind that person. Rather than force a second signup
step, the first time an employer posts a job we provision the workspace
for them -- owner membership, Starter trial -- and every later post is
governed by that workspace's plan.

Provisioning is deliberately conservative:

* it never touches the User or the ClientProfile
* it is idempotent -- a second call returns the existing workspace
* an employer who already belongs to exactly one organization is never
  given a second one
"""
from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from .models import (
    Membership,
    Organization,
    TenantPlan,
    TenantSubscription,
    TenantAuditLog,
)

logger = logging.getLogger(__name__)

TRIAL_DAYS = 30
DEFAULT_PLAN_SLUG = 'starter'


class NeedsExplicitOrganization(Exception):
    """The employer belongs to more than one workspace and must say which."""

    def __init__(self, organizations):
        self.organizations = list(organizations)
        super().__init__(
            f'This account belongs to {len(self.organizations)} organizations. '
            f'Send organization_slug to choose one.'
        )


def default_trial_plan():
    """The plan used for newly provisioned workspaces.

    Falls back to the cheapest active plan, then to any active plan, so
    provisioning still works if the Starter plan was renamed.
    """
    plan = TenantPlan.objects.filter(slug=DEFAULT_PLAN_SLUG, is_active=True).first()
    if plan:
        return plan
    return (TenantPlan.objects.filter(is_active=True)
            .order_by('price', 'sort_order').first())


def _organization_name_for(user, client_profile) -> str:
    if client_profile is not None:
        company = (getattr(client_profile, 'company_name', '') or '').strip()
        if company:
            return company
    label = user.get_full_name() or user.username
    return f'{label} (employer)'


@transaction.atomic
def provision_workspace(user, client_profile=None, plan=None) -> Organization:
    """
    Create the caller's first workspace. Idempotent per user.
    """
    existing = (
        Membership.objects
        .filter(user=user, is_active=True)
        .select_related('organization')
        .order_by('joined_at')
        .first()
    )
    if existing:
        return existing.organization

    plan = plan or default_trial_plan()
    organization = Organization.objects.create(
        name=_organization_name_for(user, client_profile),
        organization_type=Organization.TYPE_CONSTRUCTION_COMPANY,
        status=Organization.STATUS_ACTIVE,
        legal_name=(getattr(client_profile, 'company_name', '') or '')[:255],
        email=user.email or '',
        phone=(getattr(client_profile, 'phone', '') or '')[:40],
        website=(getattr(client_profile, 'website', '') or '')[:200],
        city=(getattr(client_profile, 'location', '') or '')[:120],
        country='Ethiopia',
        created_by=user,
    )

    Membership.objects.create(
        organization=organization,
        user=user,
        role=Membership.ROLE_OWNER,
        is_active=True,
        joined_at=timezone.now(),
    )

    if plan is not None:
        TenantSubscription.objects.create(
            organization=organization,
            plan=plan,
            status=TenantSubscription.STATUS_TRIALING,
            starts_at=timezone.now(),
            ends_at=timezone.now() + timezone.timedelta(days=TRIAL_DAYS),
            auto_renew=False,
        )

    TenantAuditLog.record(
        organization, user, 'organization.provisioned',
        obj=organization, source='auto',
        plan=plan.name if plan else None,
    )
    logger.info('Provisioned workspace %s for %s', organization.slug, user.username)
    return organization


def resolve_workspace(user, requested_slug=None, client_profile=None):
    """
    Work out which workspace a write should be attributed to.

    Order of preference:

    1. an explicit ``requested_slug`` -- which must be one they belong to
    2. their single existing workspace
    3. a freshly provisioned workspace
    4. ``NeedsExplicitOrganization`` if the choice is genuinely ambiguous

    Returns ``(organization, created: bool)``.
    """
    from django.core.exceptions import PermissionDenied
    from . import services

    if requested_slug:
        # get_organization raises PermissionDenied for non-members.
        return services.get_organization(user, requested_slug), False

    memberships = (
        Membership.objects
        .filter(user=user, is_active=True)
        .select_related('organization')
        .order_by('joined_at')
    )
    memberships = list(memberships)

    if len(memberships) == 1:
        return memberships[0].organization, False
    if len(memberships) > 1:
        raise NeedsExplicitOrganization([m.organization for m in memberships])

    organization = provision_workspace(user, client_profile)
    return organization, True


def visible_organizations(user):
    """Every workspace the user can read. Used to scope read endpoints."""
    from . import services

    return services.organizations_for(user)


def visible_organization_ids(user):
    return set(
        Membership.objects
        .filter(user=user, is_active=True)
        .values_list('organization_id', flat=True)
    )