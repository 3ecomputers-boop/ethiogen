from django.conf import settings
from django.db import models

from jobs.models import Job


class Application(models.Model):
    STATUS_SUBMITTED = 'submitted'
    STATUS_SCREENING = 'screening'
    STATUS_SHORTLISTED = 'shortlisted'
    STATUS_INTERVIEW = 'interview'
    STATUS_OFFER = 'offer'
    STATUS_HIRED = 'hired'
    STATUS_REJECTED = 'rejected'
    STATUS_WITHDRAWN = 'withdrawn'
    STATUS_CHOICES = [
        (STATUS_SUBMITTED, 'Submitted'),
        (STATUS_SCREENING, 'Screening'),
        (STATUS_SHORTLISTED, 'Shortlisted'),
        (STATUS_INTERVIEW, 'Interview'),
        (STATUS_OFFER, 'Offer'),
        (STATUS_HIRED, 'Hired'),
        (STATUS_REJECTED, 'Rejected'),
        (STATUS_WITHDRAWN, 'Withdrawn'),
    ]

    PIPELINE_STATUSES = [
        STATUS_SUBMITTED,
        STATUS_SCREENING,
        STATUS_SHORTLISTED,
        STATUS_INTERVIEW,
        STATUS_OFFER,
        STATUS_HIRED,
        STATUS_REJECTED,
        STATUS_WITHDRAWN,
    ]

    applicant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='applications'
    )

    job = models.ForeignKey(
        Job,
        on_delete=models.CASCADE,
        related_name='applications'
    )

    cover_letter = models.TextField()

    resume = models.FileField(
        upload_to='resumes/',
        blank=True,
        null=True
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_SUBMITTED,
        db_index=True,
    )

    applied_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-applied_at']
        indexes = [
            models.Index(fields=['job', 'status']),
        ]

    def __str__(self):
        return f"{self.applicant} → {self.job}"


class ApplicationEvent(models.Model):
    """Audit trail for an application pipeline."""

    EVENT_CREATED = 'created'
    EVENT_STATUS = 'status'
    EVENT_NOTE = 'note'
    EVENT_CHOICES = [
        (EVENT_CREATED, 'Application created'),
        (EVENT_STATUS, 'Status changed'),
        (EVENT_NOTE, 'Note added'),
    ]

    application = models.ForeignKey(
        Application,
        on_delete=models.CASCADE,
        related_name='events',
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='application_events',
    )
    event_type = models.CharField(max_length=20, choices=EVENT_CHOICES)
    from_status = models.CharField(
        max_length=20, choices=Application.STATUS_CHOICES, blank=True
    )
    to_status = models.CharField(
        max_length=20, choices=Application.STATUS_CHOICES, blank=True
    )
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['application', '-created_at']),
        ]

    def __str__(self):
        return f"{self.application_id}: {self.get_event_type_display()}"
