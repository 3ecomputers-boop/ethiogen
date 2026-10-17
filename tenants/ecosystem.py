"""
Ecosystem overview -- the platform operator's single page.

The admin's default index is a flat alphabetical list of 48 models, which
tells you nothing about how the business is doing. This aggregates the
participants that make up the marketplace (seekers, employers, brokers,
agencies) and links straight to the page that manages each one.

Superuser only.
"""
from decimal import Decimal

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import user_passes_test
from django.db.models import Count, Q, Sum
from django.shortcuts import render
from django.urls import NoReverseMatch, path, reverse
from django.utils import timezone

console_required = user_passes_test(
    lambda u: u.is_authenticated and u.is_superuser,
    login_url='/admin/login/',
)


def _card(label, value, url=None, note=''):
    return {'label': label, 'value': value, 'url': url, 'note': note}


@console_required
def ecosystem(request):
    from borker_network.models import Broker, Deal, Payout
    from billing.models import ChannelPost, IntegrationSettings, Subscription
    from employers.models import Employer
    from jobs.models import (ClientProfile, JobApplication, JobPost,
                             JobSeekerProfile, Talent)
    from tenants.models import (Membership, Organization,
                                TenantSubscription)
    from tenants.services import quota_status

    def link(model, app_label=None, name=None):
        meta = model._meta
        return reverse(f'admin:{app_label or meta.app_label}_{name or meta.model_name}_changelist')

    # ---------------------------------------------------------------- people
    seekers = JobSeekerProfile.objects.count()
    verified = JobSeekerProfile.objects.filter(is_verified=True).count()
    talents = Talent.objects.count()
    clients = ClientProfile.objects.count()
    employers = Employer.objects.count()
    brokers = Broker.objects.count()

    organizations = Organization.objects.count()
    active_orgs = Organization.objects.filter(
        status=Organization.STATUS_ACTIVE).count()

    # ---------------------------------------------------------------- money
    # The singleton settings row always lives at pk=1, but resolve the real
    # pk rather than assuming it.
    settings_row = IntegrationSettings.objects.first()
    config_url = ''
    if settings_row is not None:
        try:
            config_url = reverse(
                'admin:billing_integrationsettings_change',
                args=[settings_row.pk],
            )
        except NoReverseMatch:
            config_url = ''

    def mrr():
        total = Decimal('0')
        for sub in TenantSubscription.objects.select_related('plan'):
            if sub.is_current:
                total += sub.plan.price_per_month
        return total

    tenant_subs = [s for s in TenantSubscription.objects.select_related('plan')]
    paying = [s for s in tenant_subs if s.is_current]
    trialing = [s for s in paying if s.status == TenantSubscription.STATUS_TRIALING]
    expiring = sorted(
        [s for s in paying if s.ends_at
         and s.ends_at <= timezone.now() + timezone.timedelta(days=14)],
        key=lambda s: s.ends_at)

    global_subs = Subscription.objects.filter(
        status=Subscription.STATUS_ACTIVE).count()
    broker_revenue = Deal.objects.filter(status='completed').aggregate(
        n=Sum('commission'))['n'] or Decimal('0')

    # ---------------------------------------------------------------- activity
    posts = JobPost.objects.count()
    open_posts = JobPost.objects.filter(status='open').count()
    channel_posts = ChannelPost.objects.count()
    applications = JobApplication.objects.count()

    # ------------------------------------------------------- tenant health
    tenant_rows = []
    # subscriptions is a REVERSE relation, so it needs prefetch_related;
    # select_related only accepts forward FK/O2O and raises FieldError.
    for organization in Organization.objects.prefetch_related(
            'subscriptions__plan', 'memberships'):
        quota = quota_status(organization)
        limit = quota['job_post_limit']
        used = quota['job_posts_used']
        if not quota['has_plan']:
            health = 'no plan'
        elif quota.get('is_current') is False:
            health = 'lapsed'
        elif limit and used >= limit:
            health = 'at limit'
        else:
            health = 'ok'
        tenant_rows.append({
            'organization': organization,
            'quota': quota,
            'health': health,
            'usage_pct': round(used / limit * 100) if limit else 0,
        })

    BROKER_TIER = [
        ('seeker', 'Job seekers', seekers, link(JobSeekerProfile),
         f'{verified} verified'),
        ('employer', 'Employers', employers, link(Employer), 'employers app'),
        ('client', 'Client profiles', clients, link(ClientProfile),
         'direct advertisers'),
        ('broker', 'Brokers', brokers, link(Broker), 'network partners'),
        ('talent', 'Talent', talents, link(Talent), 'talent marketplace'),
        ('agency', 'Organizations', organizations, link(Organization),
         f'{active_orgs} active'),
    ]

    MARKETPLACE = [
        ('jobpost', 'Job listings', posts, link(JobPost),
         f'{open_posts} open'),
        ('channelpost', 'Channel posts', channel_posts, link(ChannelPost),
         'published to Telegram'),
        ('application', 'Applications', applications, link(JobApplication),
         'submitted'),
        ('deal', 'Broker deals', Deal.objects.count(), link(Deal),
         f'{broker_revenue} ETB commission'),
        ('payout', 'Broker payouts', Payout.objects.count(), link(Payout), ''),
        ('sub', 'Channel subscribers', global_subs,
         link(Subscription, name='subscription'), 'individual plans'),
    ]

    context = {
        'title': 'Ecosystem',
        'broker_tier': BROKER_TIER,
        'marketplace': MARKETPLACE,
        'config_url': config_url,
        'money': {
            'mrr': mrr(),
            'paying': len(paying),
            'trialing': len(trialing),
            'expiring': expiring,
            'broker_revenue': broker_revenue,
            'global_subs': global_subs,
        },
        'tenant_rows': tenant_rows,
        'totals': {
            'organizations': organizations,
            'members': Membership.objects.filter(is_active=True).count(),
            'plans': __import__('tenants.models', fromlist=['TenantPlan'])
                     .TenantPlan.objects.count(),
        },
        'shortcuts': [
            ('Telegram / Facebook / Chapa / Telebirr', 'billing:integrationsettings'),
            ('Organizations', 'tenants:organization'),
            ('Tenant plans', 'tenants:tenantplan'),
            ('Tenant subscriptions', 'tenants:tenantsubscription'),
            ('Workspace & audit', 'tenants:tenantauditlog'),
        ],
        'console_urls': {
            'workspaces': reverse('tenants:workspace_list'),
            'console': reverse('tenants:console_dashboard'),
            'orgs': reverse('tenants:console_organizations'),
            'plans': reverse('tenants:console_plans'),
        },
    }

    # This renders through admin/base_site.html, but it is a plain view rather
    # than an AdminSite one, so none of the admin chrome context is present and
    # the sidebar rendered empty. each_context supplies available_apps (what
    # the nav sidebar needs) plus the breadcrumbs and user-tools it expects.
    if request.user.is_active and request.user.is_staff:
        try:
            from django.contrib import admin as django_admin

            context.update(django_admin.site.each_context(request))
        except Exception:
            pass

    return render(request, 'admin/ecosystem.html', context)


urlpatterns = [
    path('ecosystem/', ecosystem, name='ecosystem'),
]


def install(admin_site):
    """
    Add /admin/ecosystem/ to the given AdminSite.

    AdminSite.get_urls() builds its own list and does not collect a
    module-level `urlpatterns`, so the view has to be appended explicitly.
    Guarded so repeated calls (e.g. autoreload) do not stack duplicates.
    """
    if getattr(admin_site, '_ethiogen_ecosystem_installed', False):
        return
    original = admin_site.get_urls

    def get_urls():
        # PREPENDED, not appended. AdminSite.get_urls() ends with a
        # catch-all `path("<path:unknown>", catch_all_view)` which matches
        # anything it sees first -- appending would make this URL resolve
        # to the catch-all and 404.
        return urlpatterns + original()

    admin_site.get_urls = get_urls
    admin_site._ethiogen_ecosystem_installed = True