from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth import get_user_model
from django.urls import path
from django.shortcuts import redirect
from django.contrib import messages
from django.utils.html import format_html

# Import your custom user and profiles
from accounts.models import User
from jobs.models import JobSeekerProfile, ClientProfile


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
    
    def user_type_badge(self, obj):
        if hasattr(obj, 'job_seeker_profile'):
            return format_html(
                '<span style="background: #3b82f6; color: white; padding: 3px 8px; '
                'border-radius: 4px; font-size: 11px;">Job Seeker</span>'
            )
        elif hasattr(obj, 'client_profile'):
            return format_html(
                '<span style="background: #10b981; color: white; padding: 3px 8px; '
                'border-radius: 4px; font-size: 11px;">Client</span>'
            )
        elif obj.is_staff:
            return format_html(
                '<span style="background: #f59e0b; color: white; padding: 3px 8px; '
                'border-radius: 4px; font-size: 11px;">Admin</span>'
            )
        return format_html(
            '<span style="background: #6b7280; color: white; padding: 3px 8px; '
            'border-radius: 4px; font-size: 11px;">Unknown</span>'
        )
    user_type_badge.short_description = 'Type'
    
    def is_verified_badge(self, obj):
        if hasattr(obj, 'job_seeker_profile') and obj.job_seeker_profile.is_verified:
            return format_html('<span style="color: #10b981; font-weight:bold;">✓</span>')
        elif hasattr(obj, 'client_profile') and obj.client_profile.is_verified:
            return format_html('<span style="color: #10b981; font-weight:bold;">✓</span>')
        return format_html('<span style="color: #ef4444;">✗</span>')
    is_verified_badge.short_description = 'Verified'

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
                name='accounts_quick_create_seeker',
            ),
            path(
                'quick-create-client/',
                self.admin_site.admin_view(self.quick_create_client_view),
                name='accounts_quick_create_client',
            ),
        ]
        return custom_urls + urls

    def quick_create_seeker_view(self, request):
        count = get_user_model().objects.count() + 1
        username = f'seeker_{count}'
        email = f'seeker{count}@example.com'
        password = 'TempPass123!'
        
        user = get_user_model().objects.create_user(
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
            f'✓ Job Seeker created!\nUsername: {username}\nPassword: {password}'
        )
        return redirect('admin:jobs_jobseekerprofile_changelist')

    def quick_create_client_view(self, request):
        count = get_user_model().objects.count() + 1
        username = f'client_{count}'
        email = f'client{count}@example.com'
        password = 'TempPass123!'
        
        user = get_user_model().objects.create_user(
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
            f'✓ Client created!\nUsername: {username}\nPassword: {password}'
        )
        return redirect('admin:jobs_clientprofile_changelist')


# ============================================================================
# UNREGISTER DEFAULT AND REGISTER CUSTOM
# ============================================================================

# We use a try/except block here so that if you ever reset your database 
# or runtests, it won't crash if the user isn't registered yet.
try:
    admin.site.unregister(get_user_model())
except admin.sites.NotRegistered:
    pass

admin.site.register(get_user_model(), CustomUserAdmin)