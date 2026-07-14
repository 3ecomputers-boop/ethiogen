from django.contrib import admin
from .models import Application


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = (
        'applicant',
        'job',
        'applied_at',
    )
    search_fields = (
        'applicant__username',
        'job__title',
    )
    list_filter = (
        'applied_at',
    )