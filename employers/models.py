from django.db import models
from django.conf import settings


class Employer(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='employer_profile'
    )
    company_name = models.CharField(max_length=255)
    website = models.URLField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Employer"
        verbose_name_plural = "Employers"
        ordering = ['company_name']

    def __str__(self):
        return self.company_name