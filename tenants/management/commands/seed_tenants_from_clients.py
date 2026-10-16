"""
Turn existing ClientProfile rows into tenant Organizations.

Why
---
You already have two real employers on the platform (Admas University and
yelbe). They predate tenancy, so they need an Organization, an owner
Membership, and a starter TenantSubscription. Their ClientProfile is kept
untouched -- it stays the public-facing company record.

This command is idempotent: re-running it does not duplicate anything.

    python manage.py seed_tenants_from_clients          # dry run
    python manage.py seed_tenants_from_clients --apply
    python manage.py seed_tenants_from_clients --apply --plan basic
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from jobs.models import ClientProfile
from tenants.models import (
    Membership,
    Organization,
    TenantPlan,
    TenantSubscription,
)

DEFAULT_PLANS = [
    {
        'name': 'Starter',
        'slug': 'starter',
        'description': 'For a single recruiter getting started.',
        'price': Decimal('1500.00'),
        'billing_cycle': TenantPlan.CYCLE_MONTHLY,
        'job_post_limit': 3,
        'seat_limit': 2,
        'featured_post_limit': 0,
        'can_use_own_channel': False,
        'can_export_data': False,
        'sort_order': 10,
    },
    {
        'name': 'Basic',
        'slug': 'basic',
        'description': 'For a growing company hiring every month.',
        'price': Decimal('4000.00'),
        'billing_cycle': TenantPlan.CYCLE_MONTHLY,
        'job_post_limit': 15,
        'seat_limit': 5,
        'featured_post_limit': 2,
        'can_use_own_channel': False,
        'can_export_data': True,
        'sort_order': 20,
    },
    {
        'name': 'Professional',
        'slug': 'professional',
        'description': 'For agencies and contractors with multiple projects.',
        'price': Decimal('9000.00'),
        'billing_cycle': TenantPlan.CYCLE_MONTHLY,
        'job_post_limit': 50,
        'seat_limit': 20,
        'featured_post_limit': 10,
        'can_use_own_channel': True,
        'can_export_data': True,
        'sort_order': 30,
    },
    {
        'name': 'Enterprise',
        'slug': 'enterprise',
        'description': 'Unlimited posting and a dedicated channel.',
        'price': Decimal('25000.00'),
        'billing_cycle': TenantPlan.CYCLE_MONTHLY,
        'job_post_limit': 0,          # unlimited
        'seat_limit': 0,              # unlimited
        'featured_post_limit': 0,
        'can_use_own_channel': True,
        'can_export_data': True,
        'sort_order': 40,
    },
]


class Command(BaseCommand):
    help = 'Create Organizations from existing ClientProfile rows.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='Actually write. Without this, nothing changes.')
        parser.add_argument('--plan', default='professional',
                            help='Plan slug for the seeded subscription '
                                 '(default: professional)')

    def handle(self, *args, **options):
        apply = options['apply']
        User = get_user_model()

        # --- plans -------------------------------------------------------
        created_plans = []
        for spec in DEFAULT_PLANS:
            plan, created = TenantPlan.objects.get_or_create(
                slug=spec['slug'], defaults=spec)
            if created:
                created_plans.append(plan.name)
        self.stdout.write(self.style.HTTP_INFO('Tenant plans'))
        if created_plans:
            self.stdout.write(f'  created: {", ".join(created_plans)}')
        else:
            self.stdout.write('  all plans already exist')
        self.stdout.write(f'  total plans: {TenantPlan.objects.count()}')
        self.stdout.write('')

        plan = TenantPlan.objects.filter(slug=options['plan']).first()
        if plan is None:
            self.stdout.write(self.style.ERROR(
                f'No plan with slug "{options["plan"]}". Available: '
                f'{", ".join(TenantPlan.objects.values_list("slug", flat=True))}'))
            return

        clients = ClientProfile.objects.select_related('user').order_by('id')
        self.stdout.write(f'  seeding from {clients.count()} ClientProfile row(s)')
        self.stdout.write(f'  subscription plan: {plan.name} '
                          f'({plan.job_post_limit or "unlimited"} posts)')
        self.stdout.write('')

        rows = []
        for client in clients:
            name = (client.company_name
                    or f"{client.user.get_full_name() or client.user.username} (employer)")
            existing = Organization.objects.filter(
                name__iexact=name,
                organization_type=Organization.TYPE_CONSTRUCTION_COMPANY,
            ).first()
            if existing:
                rows.append((name, client.user.username, 'already exists', existing.slug))
                continue
            rows.append((name, client.user.username, 'would create', ''))

        for name, username, action, slug in rows:
            self.stdout.write(f'      {action:<15} {name[:38]:<38} (owner {username})'
                              + (f'  -> /{slug}' if slug else ''))

        if not apply:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING('  DRY RUN. Re-run with --apply.'))
            return

        created_orgs = 0
        with transaction.atomic():
            for client in clients:
                name = (client.company_name
                        or f"{client.user.get_full_name() or client.user.username} (employer)")
                organization, created = Organization.objects.get_or_create(
                    name__iexact=name,
                    organization_type=Organization.TYPE_CONSTRUCTION_COMPANY,
                    defaults={
                        # `name__iexact` above is a LOOKUP -- it filters but
                        # does not set the column. Without this the created
                        # row would have name=''.
                        'name': name,
                        'status': Organization.STATUS_ACTIVE,
                        'is_verified': bool(client.is_verified),
                        'verified_at': timezone.now() if client.is_verified else None,
                        'email': client.user.email or '',
                        'phone': client.phone or '',
                        'website': client.website or '',
                        'city': client.location or '',
                        'description': client.bio or '',
                        'created_by': client.user,
                    },
                )
                if created:
                    created_orgs += 1

                membership, m_created = Membership.objects.get_or_create(
                    organization=organization,
                    user=client.user,
                    defaults={'role': Membership.ROLE_OWNER, 'is_active': True},
                )

                sub, s_created = TenantSubscription.objects.get_or_create(
                    organization=organization,
                    plan=plan,
                    status=TenantSubscription.STATUS_ACTIVE,
                    defaults={
                        'starts_at': timezone.now(),
                        'ends_at': timezone.now() + timezone.timedelta(days=30),
                        'auto_renew': True,
                    },
                )

                # Keep the public company record in step with the tenant.
                if client.company_name and not organization.legal_name:
                    organization.legal_name = client.company_name
                    organization.save(update_fields=['legal_name'])

                self.stdout.write(
                    f'      {organization.name[:32]:<32} '
                    f'org={"new" if created else "existing"} '
                    f'member={"new" if m_created else "existing"} '
                    f'sub={"new" if s_created else "existing"}'
                )

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'  {created_orgs} organization(s) created; '
            f'{Organization.objects.count()} total.'))
        self.stdout.write(f'  memberships: {Membership.objects.count()}')
        self.stdout.write(f'  subscriptions: {TenantSubscription.objects.count()}')
        self.stdout.write('')
        self.stdout.write('  No User, ClientProfile or JobSeekerProfile row was changed.')
