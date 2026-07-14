from django.db import models
from django.conf import settings

class Plan(models.Model):
    PLAN_TYPE_CHOICES = [
        ('employer', 'Employer'),
        ('job_seeker', 'Job Seeker'),
    ]
    TIER_CHOICES = [
        ('free', 'Free'),
        ('basic', 'Basic'),
        ('pro', 'Pro'),
        ('enterprise', 'Enterprise'),
    ]
    name = models.CharField(max_length=100)
    plan_type = models.CharField(max_length=20, choices=PLAN_TYPE_CHOICES)
    tier = models.CharField(max_length=20, choices=TIER_CHOICES, default='free')
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    duration_days = models.PositiveIntegerField(default=30)
    job_post_limit = models.PositiveIntegerField(default=0)   # 0 = unlimited
    application_limit = models.PositiveIntegerField(default=5) # for job seekers
    can_view_contacts = models.BooleanField(default=False)
    can_appear_in_search = models.BooleanField(default=False)
    featured_job_limit = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return f"{self.name} ({self.get_plan_type_display()})"


class Subscription(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
        ('pending', 'Pending Payment'),
    ]
    PAYMENT_METHOD_CHOICES = [
        ('card', 'Credit/Debit Card'),
        ('mobile_money', 'Mobile Money'),
        ('bank_transfer', 'Bank Transfer'),
        ('manual', 'Manual/Admin'),
    ]
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='subscriptions'
    )
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    started_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    auto_renew = models.BooleanField(default=False)
    payment_method = models.CharField(
        max_length=20, choices=PAYMENT_METHOD_CHOICES, default='manual'
    )
    payment_reference = models.CharField(max_length=100, blank=True)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} — {self.plan.name} ({self.status})"

    @property
    def is_active(self):
        from django.utils import timezone
        return self.status == 'active' and (
            self.expires_at is None or self.expires_at > timezone.now()
        )