"""
Admin pages for the jobs models that had none.

These models were created over time and never registered, so the data was
only reachable through the public site or a shell. Each gets a usable page
here: list filters, search, and sensible defaults.

Registered here:
    JobPost, JobApplication, JobCategory, ScrapedContent, TalentAccess,
    TelegramProfile, UserPreference, FavoriteWorker, WorkerPortfolio,
    WorkerVerification, WorkerAvailability
"""
from django.contrib import admin

from .models import (
    FavoriteWorker,
    JobApplication,
    JobCategory,
    JobPost,
    ScrapedContent,
    TalentAccess,
    TelegramProfile,
    UserPreference,
    WorkerAvailability,
    WorkerPortfolio,
    WorkerVerification,
)


# ======================================================================
# Jobs
# ======================================================================
@admin.register(JobPost)
class JobPostAdmin(admin.ModelAdmin):
    """Public job listings. `organization` scopes the row to a tenant."""

    list_display = ('title', 'client', 'organization', 'status', 'location',
                    'budget', 'deadline', 'created_at')
    list_filter = ('status', 'is_active', 'category', 'created_at')
    search_fields = ('title', 'description', 'location', 'client__company_name',
                     'organization__name')
    list_select_related = ('client', 'organization', 'category')
    autocomplete_fields = ()
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        (None, {'fields': ('title', 'description')}),
        ('Ownership', {
            'description': 'Leave both blank for a standalone listing. '
                           'Setting an organization makes this private to '
                           'that tenant.',
            'fields': ('client', 'organization'),
        }),
        ('Details', {'fields': ('category', 'subcategory', 'location', 'budget',
                                'deadline')}),
        ('State', {'fields': ('status', 'is_active')}),
        ('Audit', {'classes': ('collapse',),
                   'fields': ('created_at', 'updated_at')}),
    )

    @admin.display(description='applicants')
    def applicant_count(self, obj):
        return obj.applications.count()


class JobApplicationInline(admin.TabularInline):
    model = JobApplication
    extra = 0
    fields = ('job_seeker', 'status', 'bid_amount', 'applied_at')
    readonly_fields = ('applied_at',)
    autocomplete_fields = ('job_seeker',)


@admin.register(JobApplication)
class JobApplicationAdmin(admin.ModelAdmin):
    list_display = ('job', 'job_seeker', 'status', 'bid_amount', 'applied_at')
    list_filter = ('status', 'applied_at')
    search_fields = ('job__title', 'job_seeker__user__username',
                     'job_seeker__user__email')
    list_select_related = ('job', 'job_seeker')
    autocomplete_fields = ('job_seeker',)
    date_hierarchy = 'applied_at'
    readonly_fields = ('applied_at', 'updated_at')


@admin.register(JobCategory)
class JobCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    search_fields = ('name',)


@admin.register(ScrapedContent)
class ScrapedContentAdmin(admin.ModelAdmin):
    """Deduplication cache for the scraper, keyed by content hash."""

    list_display = ('url', 'short_hash', 'last_updated', 'last_posted')
    search_fields = ('url', 'content_hash')
    readonly_fields = ('content_hash', 'last_updated')
    date_hierarchy = 'last_updated'

    @admin.display(description='hash')
    def short_hash(self, obj):
        return (obj.content_hash or '')[:12]


# ======================================================================
# Talent marketplace
# ======================================================================
@admin.register(TalentAccess)
class TalentAccessAdmin(admin.ModelAdmin):
    """Paid unlock of a talent's contact details."""

    list_display = ('talent', 'employer', 'paid', 'amount', 'created_at',
                    'paid_at')
    list_filter = ('paid', 'created_at')
    search_fields = ('talent__user__username', 'employer__user__username',
                     'employer__company_name')
    list_select_related = ('talent', 'employer')
    date_hierarchy = 'created_at'


@admin.register(FavoriteWorker)
class FavoriteWorkerAdmin(admin.ModelAdmin):
    list_display = ('job_seeker', 'client', 'created_at')
    search_fields = ('job_seeker__user__username', 'client__company_name')
    list_select_related = ('job_seeker', 'client')
    date_hierarchy = 'created_at'


# ======================================================================
# Telegram / preferences
# ======================================================================
@admin.register(TelegramProfile)
class TelegramProfileAdmin(admin.ModelAdmin):
    """Links a user to their Telegram chat id for notifications."""

    list_display = ('user', 'chat_id', 'username', 'created_at')
    search_fields = ('user__username', 'user__email', 'username', 'chat_id')
    list_select_related = ('user',)
    readonly_fields = ('created_at',)

    @admin.display(description='chat id')
    def chat_id(self, obj):
        return obj.chat_id


@admin.register(UserPreference)
class UserPreferenceAdmin(admin.ModelAdmin):
    list_display = ('user', 'language', 'currency')
    search_fields = ('user__username', 'user__email')
    list_select_related = ('user',)
    autocomplete_fields = ('user',)


# ======================================================================
# Worker sub-records (OneToOne on JobSeekerProfile)
# ======================================================================
class _WorkerChildAdmin(admin.ModelAdmin):
    """Shared behaviour for the JobSeekerProfile OneToOne children."""

    search_fields = ('job_seeker__user__username', 'job_seeker__user__email')
    list_select_related = ('job_seeker',)
    autocomplete_fields = ('job_seeker',)


@admin.register(WorkerPortfolio)
class WorkerPortfolioAdmin(_WorkerChildAdmin):
    readonly_fields = ('created_at',)
    list_display = ('title', 'job_seeker', 'link', 'created_at')
    list_filter = ('created_at',)
    search_fields = _WorkerChildAdmin.search_fields + ('title', 'description')
    date_hierarchy = 'created_at'


@admin.register(WorkerVerification)
class WorkerVerificationAdmin(_WorkerChildAdmin):
    list_display = ('job_seeker', 'is_verified', 'verified_at')
    list_filter = ('is_verified', 'verified_at')
    actions = ('action_verify', 'action_unverify')

    @admin.action(description='Mark selected as verified')
    def action_verify(self, request, queryset):
        from django.utils import timezone

        n = queryset.update(is_verified=True, verified_at=timezone.now())
        self.message_user(request, f'{n} verification(s) marked verified.')

    @admin.action(description='Mark selected as unverified')
    def action_unverify(self, request, queryset):
        n = queryset.update(is_verified=False, verified_at=None)
        self.message_user(request, f'{n} verification(s) cleared.')


@admin.register(WorkerAvailability)
class WorkerAvailabilityAdmin(_WorkerChildAdmin):
    list_display = ('job_seeker', 'is_available', 'available_from',
                    'available_until')
    list_filter = ('is_available',)
    date_hierarchy = 'available_from'