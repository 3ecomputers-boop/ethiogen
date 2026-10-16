"""
Multi-tenancy, shared-table.

One database. Every organisation-scoped row carries an ``organization_id``
and every read is filtered through a membership check. No schema-per-tenant,
no database-per-tenant.

The public marketplace is deliberately NOT tenant-scoped: job seekers have
no Organization and their profiles, and public listings, stay shared.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


def invitation_expiry():
    """Default expiry for an invitation. Module level so migrations can
    serialise it (a lambda cannot be written into a migration file)."""
    return timezone.now() + timezone.timedelta(days=14)


class OrganizationQuerySet(models.QuerySet):
    def active(self):
        return self.filter(status=Organization.STATUS_ACTIVE)

    def verified(self):
        return self.filter(is_verified=True)

    def of_type(self, *types):
        return self.filter(organization_type__in=types)

    def for_user(self, user):
        """Only the organisations this user is an active member of."""
        if user is None or not getattr(user, 'is_authenticated', False):
            return self.none()
        if getattr(user, 'is_superuser', False):
            return self
        return self.filter(
            memberships__user=user,
            memberships__is_active=True,
        ).distinct()


class Organization(models.Model):
    """
    A tenant: a construction company, agency, contractor, labour supplier or
    training institution with its own private workspace.
    """

    TYPE_CONSTRUCTION_COMPANY = 'construction_company'
    TYPE_RECRUITMENT_AGENCY = 'recruitment_agency'
    TYPE_CONTRACTOR = 'contractor'
    TYPE_LABOR_SUPPLIER = 'labor_supplier'
    TYPE_TRAINING_INSTITUTION = 'training_institution'
    TYPE_CHOICES = [
        (TYPE_CONSTRUCTION_COMPANY, 'Construction company'),
        (TYPE_RECRUITMENT_AGENCY, 'Recruitment agency'),
        (TYPE_CONTRACTOR, 'Contractor / subcontractor'),
        (TYPE_LABOR_SUPPLIER, 'Labour supplier'),
        (TYPE_TRAINING_INSTITUTION, 'Training institution'),
    ]

    STATUS_PENDING = 'pending'
    STATUS_ACTIVE = 'active'
    STATUS_SUSPENDED = 'suspended'
    STATUS_CLOSED = 'closed'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending approval'),
        (STATUS_ACTIVE, 'Active'),
        (STATUS_SUSPENDED, 'Suspended'),
        (STATUS_CLOSED, 'Closed'),
    ]

    SIZE_CHOICES = [
        ('1-10', '1-10 staff'),
        ('11-50', '11-50 staff'),
        ('51-200', '51-200 staff'),
        ('201-1000', '201-1000 staff'),
        ('1000+', '1000+ staff'),
    ]

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True, blank=True)
    organization_type = models.CharField(
        max_length=32, choices=TYPE_CHOICES, default=TYPE_CONSTRUCTION_COMPANY,
        db_index=True,
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True,
    )

    legal_name = models.CharField(max_length=255, blank=True)
    registration_number = models.CharField(max_length=80, blank=True)
    description = models.TextField(blank=True)
    founded_year = models.PositiveSmallIntegerField(null=True, blank=True)
    size = models.CharField(max_length=20, choices=SIZE_CHOICES, blank=True)

    logo = models.ImageField(upload_to='tenants/logos/', null=True, blank=True)
    website = models.URLField(blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=120, blank=True)
    country = models.CharField(max_length=120, blank=True, default='Ethiopia')

    # Optional: give a large tenant its own Telegram channel.
    telegram_chat_id = models.CharField(max_length=64, blank=True)

    is_verified = models.BooleanField(default=False, db_index=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='verified_organizations',
    )

    # Free-form per-tenant configuration (branding, notification rules, ...).
    settings_json = models.JSONField(default=dict, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_organizations',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = OrganizationQuerySet.as_manager()

    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['organization_type', 'status']),
            models.Index(fields=['is_verified']),
        ]

    def __str__(self):
        return f'{self.name} ({self.get_organization_type_display()})'

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name)[:180] or 'org'
            slug = base
            n = 2
            while (Organization.objects
                   .filter(slug=slug)
                   .exclude(pk=self.pk)
                   .exists()):
                slug = f'{base}-{n}'
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)

    # -- membership helpers ------------------------------------------
    def member_users(self):
        return (settings.AUTH_USER_MODEL.objects
                .filter(memberships__organization=self,
                        memberships__is_active=True)
                .distinct())

    def has_member(self, user) -> bool:
        if user is None or not getattr(user, 'is_authenticated', False):
            return False
        if getattr(user, 'is_superuser', False):
            return True
        return self.memberships.filter(user=user, is_active=True).exists()

    def role_for(self, user):
        if user is None or not getattr(user, 'is_authenticated', False):
            return None
        if getattr(user, 'is_superuser', False):
            return Membership.ROLE_OWNER
        membership = self.memberships.filter(user=user, is_active=True).first()
        return membership.role if membership else None


class MembershipQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)


class Membership(models.Model):
    """Links a user to an organisation with a role inside that workspace."""

    ROLE_OWNER = 'owner'
    ROLE_ADMIN = 'admin'
    ROLE_RECRUITER = 'recruiter'
    ROLE_HIRING_MANAGER = 'hiring_manager'
    ROLE_BILLING = 'billing'
    ROLE_VIEWER = 'viewer'
    ROLE_CHOICES = [
        (ROLE_OWNER, 'Owner'),
        (ROLE_ADMIN, 'Administrator'),
        (ROLE_RECRUITER, 'Recruiter'),
        (ROLE_HIRING_MANAGER, 'Hiring manager'),
        (ROLE_BILLING, 'Billing contact'),
        (ROLE_VIEWER, 'Viewer'),
    ]

    # What each role may do inside the workspace.
    CAPABILITIES = {
        ROLE_OWNER: {'view', 'edit', 'manage_members', 'manage_billing', 'publish', 'delete'},
        ROLE_ADMIN: {'view', 'edit', 'manage_members', 'publish', 'delete'},
        ROLE_RECRUITER: {'view', 'publish'},
        ROLE_HIRING_MANAGER: {'view', 'publish'},
        ROLE_BILLING: {'view', 'manage_billing'},
        ROLE_VIEWER: {'view'},
    }

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='memberships'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='memberships'
    )
    role = models.CharField(max_length=24, choices=ROLE_CHOICES, default=ROLE_VIEWER)
    is_active = models.BooleanField(default=True, db_index=True)

    job_title = models.CharField(max_length=120, blank=True)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='sent_membership_invitations',
    )
    joined_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = MembershipQuerySet.as_manager()

    class Meta:
        unique_together = [('organization', 'user')]
        ordering = ['organization', 'role']
        indexes = [models.Index(fields=['user', 'is_active'])]

    def __str__(self):
        return f'{self.user} @ {self.organization} ({self.role})'

    def can(self, capability: str) -> bool:
        return capability in self.CAPABILITIES.get(self.role, set())


class Invitation(models.Model):
    """An email invitation to join an organisation workspace."""

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='invitations'
    )
    email = models.EmailField()
    role = models.CharField(max_length=24, choices=Membership.ROLE_CHOICES,
                            default=Membership.ROLE_VIEWER)
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='sent_tenant_invitations',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=invitation_expiry)
    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='accepted_tenant_invitations',
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.email} -> {self.organization}'

    @property
    def is_open(self) -> bool:
        return (self.accepted_at is None
                and self.expires_at > timezone.now())


class TenantPlan(models.Model):
    """A subscription plan an organisation can buy."""

    CYCLE_MONTHLY = 'monthly'
    CYCLE_ANNUAL = 'annual'
    CYCLE_CHOICES = [
        (CYCLE_MONTHLY, 'Monthly'),
        (CYCLE_ANNUAL, 'Annual'),
    ]

    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    description = models.TextField(blank=True)

    # Empty tuple means the plan applies to every tenant type.
    applies_to = models.JSONField(default=list, blank=True,
                                  help_text='List of organization_type values. '
                                            'Empty = all types.')
    price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    billing_cycle = models.CharField(max_length=16, choices=CYCLE_CHOICES,
                                     default=CYCLE_MONTHLY)

    # 0 means unlimited.
    job_post_limit = models.PositiveIntegerField(default=0)
    seat_limit = models.PositiveIntegerField(default=1)
    featured_post_limit = models.PositiveIntegerField(default=0)
    can_use_own_channel = models.BooleanField(default=False)
    can_export_data = models.BooleanField(default=False)

    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'price']

    def __str__(self):
        return f'{self.name} ({self.get_billing_cycle_display()})'

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:120]
        super().save(*args, **kwargs)

    def applies_to_type(self, organization_type: str) -> bool:
        types = self.applies_to or []
        return (not types) or (organization_type in types)

    @property
    def price_per_month(self) -> Decimal:
        if self.billing_cycle == self.CYCLE_ANNUAL:
            return (self.price / Decimal(12)).quantize(Decimal('0.01'))
        return self.price


class TenantSubscription(models.Model):
    """What an organisation has paid for. This is the recurring revenue."""

    STATUS_TRIALING = 'trialing'
    STATUS_ACTIVE = 'active'
    STATUS_PAST_DUE = 'past_due'
    STATUS_CANCELLED = 'cancelled'
    STATUS_EXPIRED = 'expired'
    STATUS_CHOICES = [
        (STATUS_TRIALING, 'Trialing'),
        (STATUS_ACTIVE, 'Active'),
        (STATUS_PAST_DUE, 'Past due'),
        (STATUS_CANCELLED, 'Cancelled'),
        (STATUS_EXPIRED, 'Expired'),
    ]

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='subscriptions'
    )
    plan = models.ForeignKey(
        TenantPlan, on_delete=models.PROTECT, related_name='subscriptions'
    )
    status = models.CharField(max_length=16, choices=STATUS_CHOICES,
                              default=STATUS_ACTIVE, db_index=True)
    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField(null=True, blank=True)
    auto_renew = models.BooleanField(default=True)
    cancel_at_period_end = models.BooleanField(default=False)

    # Counters for quota enforcement.
    job_posts_used = models.PositiveIntegerField(default=0)
    seats_used = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['organization', 'status'])]

    def __str__(self):
        return f'{self.organization} — {self.plan} ({self.status})'

    @property
    def is_current(self) -> bool:
        if self.status not in (self.STATUS_ACTIVE, self.STATUS_TRIALING,
                               self.STATUS_PAST_DUE):
            return False
        return self.ends_at is None or self.ends_at > timezone.now()

    @property
    def days_remaining(self) -> int:
        if not self.ends_at:
            return -1  # unlimited
        return max(0, (self.ends_at - timezone.now()).days)


class TenantAuditLog(models.Model):
    """Who did what inside which tenant."""

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='audit_logs'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='tenant_audit_logs',
    )
    action = models.CharField(max_length=60, db_index=True)
    object_type = models.CharField(max_length=60, blank=True)
    object_id = models.CharField(max_length=64, blank=True)
    detail = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization', 'created_at']),
            models.Index(fields=['organization', 'action']),
        ]

    def __str__(self):
        who = self.user or 'system'
        return f'{who} {self.action} on {self.organization}'

    @classmethod
    def record(cls, organization, user, action, obj=None, request=None, **detail):
        """
        Best-effort audit write. Never raises -- but it LOGS, because a
        silent audit failure is worse than a noisy one.
        """
        import logging

        log = logging.getLogger(__name__)
        ip = agent = ''
        if request is not None:
            ip = (request.META.get('REMOTE_ADDR') or '')[:45]
            agent = (request.META.get('HTTP_USER_AGENT') or '')[:255]
        try:
            return cls.objects.create(
                organization=organization,
                user=user if getattr(user, 'is_authenticated', False) else None,
                action=action,
                object_type=obj.__class__.__name__ if obj is not None else '',
                object_id=str(getattr(obj, 'pk', '') or ''),
                detail=detail,
                ip_address=ip or None,
                user_agent=agent,
            )
        except Exception as exc:
            log.error(
                'Audit write failed (action=%s org=%s): %s',
                action, getattr(organization, 'pk', None), exc, exc_info=True,
            )
            return None
