from django.contrib import admin, messages
from django.utils.html import format_html, mark_safe

from .models import (
    Invitation,
    Membership,
    Organization,
    TenantAuditLog,
    TenantPlan,
    TenantSubscription,
)
from .services import quota_status


class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 0
    fields = ('user', 'role', 'job_title', 'is_active', 'joined_at')
    autocomplete_fields = ('user',)
    readonly_fields = ('joined_at',)


class TenantSubscriptionInline(admin.TabularInline):
    model = TenantSubscription
    extra = 0
    fields = ('plan', 'status', 'starts_at', 'ends_at', 'job_posts_used', 'auto_renew')
    readonly_fields = ('starts_at',)


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'organization_type', 'status', 'is_verified',
        'member_count', 'job_post_quota', 'created_at',
    )
    list_filter = ('organization_type', 'status', 'is_verified')
    search_fields = ('name', 'legal_name', 'registration_number', 'email',
                      'city', 'slug')
    # NOTE: no prepopulated_fields for `slug` -- it is readonly because
    # Organization.save() derives it from the name. Referencing a readonly
    # field in prepopulated_fields raises KeyError when the form is built.
    readonly_fields = ('slug', 'created_at', 'updated_at', 'quota_summary')
    inlines = (MembershipInline, TenantSubscriptionInline)
    actions = ('action_verify', 'action_suspend', 'action_activate')

    fieldsets = (
        (None, {'fields': ('name', 'slug', 'organization_type', 'status', 'size')}),
        ('Identity', {
            'fields': ('legal_name', 'registration_number', 'founded_year',
                       'description'),
        }),
        ('Contact', {
            'fields': ('logo', 'website', 'email', 'phone', 'address',
                       'city', 'country'),
        }),
        ('Verification', {
            'fields': ('is_verified', 'verified_at', 'verified_by'),
        }),
        ('Integrations', {
            'classes': ('collapse',),
            'fields': ('telegram_chat_id', 'settings_json'),
        }),
        (None, {
            'description': 'Current plan limits and usage, calculated from the '
                           'live subscription.',
            'fields': ('quota_summary',),
        }),
        ('Audit', {
            'classes': ('collapse',),
            'fields': ('created_by', 'created_at', 'updated_at'),
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('memberships')

    @admin.display(description='Members')
    def member_count(self, obj):
        return obj.memberships.filter(is_active=True).count()

    @admin.display(description='Job post quota')
    def job_post_quota(self, obj):
        quota = quota_status(obj)
        if not quota['has_plan']:
            return mark_safe('<span style="color:#dc2626;font-weight:700">no plan</span>')
        remaining = quota['job_posts_remaining']
        if remaining < 0:
            detail = 'unlimited'
        else:
            detail = f"{quota['job_posts_used']}/{quota['job_post_limit']}"
        colour = '#16a34a' if (remaining < 0 or remaining > 0) else '#dc2626'
        # Interpolated values go through format_html's {} so they get escaped;
        # the surrounding markup is ours and is trusted.
        return format_html(
            '<span style="color:{};font-weight:700">{}</span>', colour, detail)

    @admin.display(description='Quota')
    def quota_summary(self, obj):
        if not obj.pk:
            return '(save first)'
        q = quota_status(obj)
        rows = [
            ('Plan', q['plan'] or 'none'),
            ('Status', q.get('status', '-')),
            ('Job posts', (f"{q['job_posts_used']} used, "
                           f"{'unlimited' if q['job_post_limit'] == 0 else q['job_post_limit']}")),
            ('Seats', f"{q['seats_used']} / {q['seat_limit'] or 'unlimited'}"),
            ('Days remaining', q.get('days_remaining', '-')),
        ]
        body = ''.join(
            f'<tr><td style="padding:3px 12px 3px 0"><b>{k}</b></td>'
            f'<td style="padding:3px 0">{v}</td></tr>'
            for k, v in rows
        )
        # `body` is markup we build above from plan names and counts, so it is
        # trusted; mark_safe on the whole table would be wrong because the
        # interpolated values are escaped.
        return format_html('<table style="font-size:12px">{}</table>', mark_safe(body))

    @admin.action(description='Verify selected organizations')
    def action_verify(self, request, queryset):
        from django.utils import timezone

        n = queryset.update(is_verified=True, verified_at=timezone.now(),
                            verified_by=request.user)
        self.message_user(request, f'{n} organization(s) verified.', messages.SUCCESS)

    @admin.action(description='Suspend selected organizations')
    def action_suspend(self, request, queryset):
        n = queryset.update(status=Organization.STATUS_SUSPENDED)
        self.message_user(request, f'{n} organization(s) suspended.', messages.WARNING)

    @admin.action(description='Reactivate selected organizations')
    def action_activate(self, request, queryset):
        n = queryset.update(status=Organization.STATUS_ACTIVE)
        self.message_user(request, f'{n} organization(s) reactivated.', messages.SUCCESS)


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ('user', 'organization', 'role', 'is_active', 'joined_at')
    list_filter = ('role', 'is_active', 'organization__organization_type')
    search_fields = ('user__username', 'user__email', 'organization__name')
    autocomplete_fields = ('user',)
    list_select_related = ('organization', 'user')


@admin.register(Invitation)
class InvitationAdmin(admin.ModelAdmin):
    list_display = ('email', 'organization', 'role', 'is_open', 'created_at',
                    'expires_at', 'accepted_at')
    list_filter = ('role', 'organization')
    search_fields = ('email', 'organization__name')
    readonly_fields = ('token', 'created_at', 'expires_at', 'accepted_at', 'accepted_by')
    list_select_related = ('organization',)


@admin.register(TenantPlan)
class TenantPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'price', 'billing_cycle', 'price_per_month',
                    'job_post_limit', 'seat_limit', 'is_active', 'sort_order')
    list_filter = ('billing_cycle', 'is_active')
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}

    @admin.display(description='Price / month')
    def price_per_month(self, obj):
        return obj.price_per_month


@admin.register(TenantSubscription)
class TenantSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('organization', 'plan', 'status', 'starts_at', 'ends_at',
                    'job_posts_used', 'is_current', 'auto_renew')
    list_filter = ('status', 'plan', 'auto_renew')
    search_fields = ('organization__name',)
    list_select_related = ('organization', 'plan')
    readonly_fields = ('created_at', 'updated_at')

    @admin.display(boolean=True, description='Current')
    def is_current(self, obj):
        return obj.is_current


@admin.register(TenantAuditLog)
class TenantAuditLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'organization', 'user', 'action', 'object_type',
                    'object_id')
    list_filter = ('action', 'organization')
    search_fields = ('organization__name', 'user__username', 'action')
    list_select_related = ('organization', 'user')
    readonly_fields = [f.name for f in TenantAuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
