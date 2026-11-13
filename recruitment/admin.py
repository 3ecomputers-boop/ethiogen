from django.contrib import admin

from .models import Application, ApplicationEvent


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = (
        'applicant',
        'job',
        'status',
        'applied_at',
        'updated_at',
    )
    search_fields = (
        'applicant__username',
        'job__title',
    )
    list_filter = (
        'status',
        'applied_at',
    )


@admin.register(ApplicationEvent)
class ApplicationEventAdmin(admin.ModelAdmin):
    list_display = (
        'application',
        'event_type',
        'from_status',
        'to_status',
        'actor',
        'created_at',
    )
    list_filter = ('event_type', 'created_at')
    search_fields = (
        'application__applicant__username',
        'application__job__title',
        'note',
    )
    readonly_fields = (
        'application',
        'actor',
        'event_type',
        'from_status',
        'to_status',
        'note',
        'created_at',
    )
