from django.apps import AppConfig


class TenantsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'tenants'
    verbose_name = 'Tenant organizations'

    def ready(self):
        # Adds /admin/ecosystem/ to the default admin site.
        from django.contrib import admin

        from . import ecosystem

        ecosystem.install(admin.site)
