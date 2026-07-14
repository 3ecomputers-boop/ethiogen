from django.db import models
from django.conf import settings


class Skill(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class FreelancerProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="freelancer_profile"
    )
    skills = models.ManyToManyField(
        Skill,
        blank=True,
        related_name="freelancers"
    )
    bio = models.TextField(blank=True)
    portfolio_url = models.URLField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Freelancer Profile"
        verbose_name_plural = "Freelancer Profiles"

    def __str__(self):
        return self.user.get_username()


class JobPosting(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField()
    budget = models.DecimalField(max_digits=12, decimal_places=2)
    deadline = models.DateField()

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="job_postings"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class Bid(models.Model):
    freelancer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="bids"
    )

    job_posting = models.ForeignKey(
        JobPosting,
        on_delete=models.CASCADE,
        related_name="bids"
    )

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    proposal = models.TextField()
    date_submitted = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_submitted"]
        unique_together = ("freelancer", "job_posting")

    def __str__(self):
        return f"{self.freelancer} - {self.job_posting.title}"