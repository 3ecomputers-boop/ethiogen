from django.db import models
from django.conf import settings
from jobs.models import Job


class Application(models.Model):
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

    applied_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-applied_at']

    def __str__(self):
        return f"{self.applicant} → {self.job}"