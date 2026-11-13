from django.apps import AppConfig


class RecruitmentConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'recruitment'

    def ready(self):
        # Registers the application audit-event signals.
        from . import signals  # noqa: F401
