from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.urls import path
from django.shortcuts import redirect
from django.contrib import messages
from django.utils.html import format_html, mark_safe

from .models import (
    JobSeekerProfile, ClientProfile, Talent, HireRequest, 
    PostNeedRequest, Job, Message, Review, Profession, 
    Category, SubCategory, Booking, WorkerRating
)

User = get_user_model()


# ============================================================================
# INLINES (For User Admin)
# ============================================================================

class JobSeekerInline(admin.StackedInline):
    model = JobSeekerProfile
    can_delete = False
    verbose_name_plural = 'Job Seeker Profile'
    fk_name = 'user'
    
    fieldsets = (
        ('Professional Information', {
            'fields': ('title', 'profession', 'bio', 'profile_picture')
        }),
        ('Location', {
            'fields': ('country', 'city', 'location')
        }),
        ('Professional Details', {
            'fields': (
                'category', 'subcategory', 'hourly_rate', 
                'years_of_experience', 'skills', 'resume'
            )
        }),
        ('Verification Status', {
            'fields': ('is_verified', 'email_verified', 'phone_verified', 'phone_number'),
            'description': '⚠️ Admins can manually verify users here (bypasses OTP).'
        }),
    )


class ClientProfileInline(admin.StackedInline):
    model = ClientProfile
    can_delete = False
    verbose_name_plural = 'Client Profile'
    fk_name = 'user'
    
    fieldsets = (
        ('Company Information', {
            'fields': ('company_name', 'location', 'phone', 'website', 'bio')
        }),
        ('Verification Status', {
            'fields': ('is_verified',),
            'description': '⚠️ Admins can manually verify clients here.'
        }),
    )


# ============================================================================
# USER ADMIN (Central Hub)
# ============================================================================

class CustomUserAdmin(BaseUserAdmin):
    inlines = (JobSeekerInline, ClientProfileInline)
    
    list_display = (
        'username', 'email', 'first_name', 'last_name', 
        'user_type_badge', 'is_verified_badge', 'is_active', 'date_joined'
    )
    list_filter = ('is_active', 'is_staff', 'is_superuser', 'groups')
    search_fields = ('username', 'email', 'first_name', 'last_name')
    
    @admin.display(description='Type')
    def user_type_badge(self, obj):
        if hasattr(obj, 'job_seeker_profile'):
            return mark_safe(
                '<span style="background: #3b82f6; color: white; padding: 3px 8px; '
                'border-radius: 4px; font-size: 11px;">Job Seeker</span>'
            )
        elif hasattr(obj, 'client_profile'):
            return mark_safe(
                '<span style="background: #10b981; color: white; padding: 3px 8px; '
                'border-radius: 4px; font-size: 11px;">Client</span>'
            )
        elif obj.is_staff:
            return mark_safe(
                '<span style="background: #f59e0b; color: white; padding: 3px 8px; '
                'border-radius: 4px; font-size: 11px;">Admin</span>'
            )
        return mark_safe(
            '<span style="background: #6b7280; color: white; padding: 3px 8px; '
            'border-radius: 4px; font-size: 11px;">Unknown</span>'
        )
    
    @admin.display(description='Verified')
    def is_verified_badge(self, obj):
        if hasattr(obj, 'job_seeker_profile') and obj.job_seeker_profile.is_verified:
            return mark_safe('<span style="color: #10b981; font-weight:bold;">✓</span>')
        elif hasattr(obj, 'client_profile') and obj.client_profile.is_verified:
            return mark_safe('<span style="color: #10b981; font-weight:bold;">✓</span>')
        return mark_safe('<span style="color: #ef4444;">✗</span>')

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for instance in instances:
            if isinstance(instance, (JobSeekerProfile, ClientProfile)):
                instance.is_verified = True
                instance.is_active = True
                if isinstance(instance, JobSeekerProfile):
                    instance.email_verified = True
                    instance.phone_verified = True
                    instance.otp_code = None
                    instance.otp_expires_at = None
                instance.save()
        formset.save_m2m()

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'quick-create-seeker/',
                self.admin_site.admin_view(self.quick_create_seeker_view),
                name='jobs_quick_create_seeker',
            ),
            path(
                'quick-create-client/',
                self.admin_site.admin_view(self.quick_create_client_view),
                name='jobs_quick_create_client',
            ),
        ]
        return custom_urls + urls

    def quick_create_seeker_view(self, request):
        count = User.objects.count() + 1
        username = f'seeker_{count}'
        email = f'seeker{count}@example.com'
        password = 'TempPass123!'
        
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name='New',
            last_name=f'Seeker{count}',
            is_active=True
        )
        
        JobSeekerProfile.objects.create(
            user=user,
            title='Professional',
            is_verified=True,
            email_verified=True,
            is_active=True
        )
        
        messages.success(
            request,
            format_html('✓ Job Seeker created!<br>Username: <b>{}</b><br>Password: <b>{}</b>', username, password)
        )
        return redirect('admin:jobs_jobseekerprofile_changelist')

    def quick_create_client_view(self, request):
        count = User.objects.count() + 1
        username = f'client_{count}'
        email = f'client{count}@example.com'
        password = 'TempPass123!'
        
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name='New',
            last_name=f'Client{count}',
            is_active=True
        )
        
        ClientProfile.objects.create(
            user=user,
            company_name=f'Company {count}',
            is_verified=True
        )
        
        messages.success(
            request,
            format_html('✓ Client created!<br>Username: <b>{}</b><br>Password: <b>{}</b>', username, password)
        )
        return redirect('admin:jobs_clientprofile_changelist')


# ============================================================================
# JOB SEEKER PROFILE ADMIN
# ============================================================================

@admin.register(JobSeekerProfile)
class JobSeekerProfileAdmin(admin.ModelAdmin):
    list_display = (
        'user_link', 'title', 'country', 'city',
        'is_verified', 'email_verified', 'is_active',
        'created_at'
    )
    list_filter = ('is_verified', 'email_verified', 'is_active', 'country', 'category')
    search_fields = ('user__username', 'user__email', 'user__first_name', 'title', 'city')
    readonly_fields = ('created_at', 'updated_at', 'otp_code', 'otp_created_at', 'otp_expires_at', 'otp_attempts')
    raw_id_fields = ('user',)
    list_editable = ('is_verified', 'is_active')
    
    fieldsets = (
        ('User Account', {'fields': ('user',)}),
        ('Professional Info', {'fields': ('title', 'profession', 'bio', 'profile_picture')}),
        ('Location', {'fields': ('country', 'city', 'location')}),
        ('Professional Details', {
            'fields': (
                'category', 'subcategory', 'hourly_rate',
                'years_of_experience', 'skills', 'resume'
            )
        }),
        ('Verification & Security', {
            'fields': (
                'is_verified', 'email_verified', 'phone_verified',
                'phone_number', 'is_active'
            ),
            'description': '💡 Admin controls bypass OTP requirements.'
        }),
        ('OTP Logs (Read Only)', {
            'fields': ('otp_code', 'otp_created_at', 'otp_expires_at', 'otp_attempts'),
            'classes': ('collapse',),
        }),
        ('Timestamps', {'fields': ('created_at', 'updated_at')}),
    )

    @admin.display(description='User', ordering='user__username')
    def user_link(self, obj):
        return format_html('<a href="/admin/auth/user/{}/change/">{}</a>', obj.user_id, obj.user.username)

    def save_model(self, request, obj, form, change):
        obj.is_verified = True
        obj.is_active = True
        if obj.otp_code:
            obj.otp_code = None
            obj.otp_expires_at = None
            obj.otp_attempts = 0
        if obj.user:
            obj.user.is_active = True
            obj.user.save()
        super().save_model(request, obj, form, change)

    @admin.action(description="✓ Mark selected as Verified")
    def verify_selected(self, request, queryset):
        updated = queryset.update(is_verified=True, email_verified=True)
        self.message_user(request, f'{updated} users verified.')

    @admin.action(description="⚡ Activate selected users")
    def activate_selected(self, request, queryset):
        updated = queryset.update(is_active=True)
        user_ids = queryset.values_list('user_id', flat=True)
        User.objects.filter(id__in=user_ids).update(is_active=True)
        self.message_user(request, f'{updated} users activated.')


# ============================================================================
# CLIENT PROFILE ADMIN
# ============================================================================

@admin.register(ClientProfile)
class ClientProfileAdmin(admin.ModelAdmin):
    list_display = ('user_link', 'company_name', 'is_verified', 'created_at')
    list_filter = ('is_verified',)
    search_fields = ('user__username', 'user__email', 'company_name')
    readonly_fields = ('created_at', 'updated_at')
    raw_id_fields = ('user',)
    list_editable = ('is_verified',)

    @admin.display(description='User')
    def user_link(self, obj):
        return format_html('<a href="/admin/auth/user/{}/change/">{}</a>', obj.user_id, obj.user.username)

    def save_model(self, request, obj, form, change):
        obj.is_verified = True
        if obj.user:
            obj.user.is_active = True
            obj.user.save()
        super().save_model(request, obj, form, change)

    @admin.action(description="✅ Verify Selected")
    def verify_selected_clients(self, request, queryset):
        updated = queryset.update(is_verified=True)
        self.message_user(request, f'{updated} companies verified successfully!')


# ============================================================================
# JOB ADMIN (Unified)
# ============================================================================

@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'company_name', 'is_approved', 'is_completed',
        'employment_type', 'location', 'posted_date'
    )
    list_filter = ('employment_type', 'is_approved', 'is_completed', 'posted_date')
    search_fields = ('title', 'company_name', 'location', 'description')
    list_editable = ('is_approved', 'is_completed')
    date_hierarchy = 'posted_date'
    ordering = ('-posted_date',)

    @admin.action(description="✅ Approve Selected")
    def approve_selected_jobs(self, request, queryset):
        updated = queryset.update(is_approved=True)
        self.message_user(request, f'{updated} jobs approved successfully!')


# ============================================================================
# TALENT MARKETPLACE ADMIN
# ============================================================================

@admin.register(Talent)
class TalentAdmin(admin.ModelAdmin):
    list_display = ('name', 'role', 'category', 'rating', 'verified', 'top', 'tier')
    list_filter = ('category', 'verified', 'top', 'tier')
    search_fields = ('name', 'role', 'bio')
    list_editable = ('verified', 'top')


@admin.register(HireRequest)
class HireRequestAdmin(admin.ModelAdmin):
    list_display = ('company_name', 'talent_name', 'status', 'budget', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('company_name', 'email')

    @admin.display(description='Talent')
    def talent_name(self, obj):
        return obj.talent.name if obj.talent else 'N/A'


@admin.register(PostNeedRequest)
class PostNeedRequestAdmin(admin.ModelAdmin):
    list_display = ('job_title', 'budget', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('job_title',)


# ============================================================================
# COMMUNICATION & RATINGS
# ============================================================================

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('sender', 'recipient', 'truncated_message', 'timestamp')
    list_filter = ('timestamp', 'is_read')
    search_fields = ('sender__username', 'recipient__username', 'message')

    @admin.display(description='Message')
    def truncated_message(self, obj):
        return f"{obj.message[:50]}..." if len(obj.message) > 50 else obj.message


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('job', 'client', 'provider', 'rating', 'timestamp')
    list_filter = ('rating', 'timestamp')
    
    @admin.display(description='Provider')
    def provider(self, obj):
        return obj.service_provider.get_full_name()


@admin.register(WorkerRating)
class WorkerRatingAdmin(admin.ModelAdmin):
    list_display = ('worker', 'client', 'rating', 'created_at')
    list_filter = ('rating',)

    @admin.display(description='Worker')
    def worker(self, obj):
        return obj.job_seeker.get_full_name()


# ============================================================================
# SUPPORTING MODELS
# ============================================================================

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'name_am')
    search_fields = ('name',)


@admin.register(SubCategory)
class SubCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'category')
    list_filter = ('category',)


@admin.register(Profession)
class ProfessionAdmin(admin.ModelAdmin):
    search_fields = ('name',)


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('job', 'service_provider', 'status', 'start_date')
    list_filter = ('status', 'start_date')
    raw_id_fields = ('job', 'service_provider', 'client')


# ============================================================================
# OVERRIDE DEFAULT USER ADMIN (must be last)
# ============================================================================
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)