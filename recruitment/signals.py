"""Audit events for recruitment applications."""
from __future__ import annotations

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import Application, ApplicationEvent


@receiver(pre_save, sender=Application)
def capture_previous_status(sender, instance, raw=False, **kwargs):
    if raw or not instance.pk:
        return
    instance._previous_status = (
        Application.objects
        .filter(pk=instance.pk)
        .values_list('status', flat=True)
        .first()
    )


@receiver(post_save, sender=Application)
def record_application_event(sender, instance, created, raw=False, **kwargs):
    if raw:
        return

    if created:
        ApplicationEvent.objects.create(
            application=instance,
            actor=instance.applicant,
            event_type=ApplicationEvent.EVENT_CREATED,
            to_status=instance.status,
        )
        return

    previous = getattr(instance, '_previous_status', None)
    if previous and previous != instance.status:
        ApplicationEvent.objects.create(
            application=instance,
            actor=getattr(instance, '_event_actor', None),
            event_type=ApplicationEvent.EVENT_STATUS,
            from_status=previous,
            to_status=instance.status,
        )
