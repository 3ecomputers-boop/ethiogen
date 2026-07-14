"""
Jobs App Models
Complete model definitions for the MoyaJobs platform.
"""

import random
import string
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django_countries.fields import CountryField


# ============================================================================
# CATEGORY & PROFESSION MODELS
# ============================================================================

class Category(models.Model):
    """Main job category (e.g., Construction, IT, Healthcare)."""
    name = models.CharField(max_length=100, db_index=True)
    name_am = models.CharField(max_length=100, blank=True, help_text="Amharic translation")
    description = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ['name']

    def __str__(self):
        return self.name


class SubCategory(models.Model):
    """Subcategory under a main category."""
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='subcategories')
    name = models.CharField(max_length=100, db_index=True)
    name_am = models.CharField(max_length=100, blank=True)

    class Meta:
        verbose_name_plural = "Subcategories"
        ordering = ['category__name', 'name']

    def __str__(self):
        return f"{self.category.name} → {self.name}"


class JobCategory(models.Model):
    """Legacy/Simple job category model."""
    name = models.CharField(max_length=100, db_index=True)
    description = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name_plural = "Job Categories"
        ordering = ['name']

    def __str__(self):
        return self.name


class Profession(models.Model):
    """Professional role/title (e.g., Developer, Engineer, Designer)."""
    name = models.CharField(max_length=100, db_index=True)
    description = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


# ============================================================================
# USER PROFILE MODELS
# ============================================================================

class ClientProfile(models.Model):
    """Profile for clients/employers who post jobs."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='client_profile'
    )
    company_name = models.CharField(max_length=255, blank=True, null=True)
    location = models.CharField(max_length=255, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    website = models.URLField(blank=True, null=True)
    bio = models.TextField(blank=True, null=True)
    is_verified = models.BooleanField(default=False, help_text="Admin‑approved client status", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Client Profile"
        verbose_name_plural = "Client Profiles"

    def __str__(self):
        return f"{self.user.username} - {self.company_name or 'Client'}"

    def get_absolute_url(self):
        return reverse('jobs:client_profile', kwargs={'pk': self.pk})


class JobSeekerProfile(models.Model):
    """Profile for job seekers with OTP verification."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='job_seeker_profile'
    )

    # Professional Information
    title = models.CharField(max_length=200, blank=True, help_text="Professional title/role")
    profession = models.ForeignKey(
        Profession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='job_seekers'
    )
    bio = models.TextField(blank=True)
    profile_picture = models.ImageField(upload_to='profiles/', blank=True, null=True)

    # Location
    country = CountryField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    location = models.CharField(max_length=255, blank=True, help_text="Full location string")

    # Professional Details
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='job_seekers'
    )
    subcategory = models.ForeignKey(
        SubCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='job_seekers'
    )
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    price_per_unit = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    price_unit = models.CharField(
        max_length=50,
        choices=[('Hour', 'Hour'), ('Day', 'Day'), ('Week', 'Week'), ('Month', 'Month')],
        blank=True
    )
    years_of_experience = models.IntegerField(default=0, help_text="Experience in years")
    skills = models.JSONField(default=list, blank=True)
    resume = models.FileField(upload_to='resumes/', blank=True, null=True)

    # Rating & Verification
    average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)
    is_verified = models.BooleanField(default=False, help_text="Admin‑verified job seeker", db_index=True)
    phone_number = models.CharField(max_length=20, blank=True)
    email_verified = models.BooleanField(default=False, db_index=True)
    phone_verified = models.BooleanField(default=False)

    # OTP Fields
    otp_code = models.CharField(max_length=6, blank=True, null=True)
    otp_created_at = models.DateTimeField(blank=True, null=True)
    otp_attempts = models.IntegerField(default=0)
    otp_expires_at = models.DateTimeField(blank=True, null=True)

    # Status
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Job Seeker Profile"
        verbose_name_plural = "Job Seeker Profiles"
        indexes = [
            models.Index(fields=['is_verified', 'is_active']),
            models.Index(fields=['country', 'city']),
        ]

    def generate_otp(self):
        """Generate a 6-digit OTP valid for 10 minutes."""
        self.otp_code = ''.join(random.choices(string.digits, k=6))
        self.otp_created_at = timezone.now()
        self.otp_expires_at = timezone.now() + timedelta(minutes=10)
        self.otp_attempts = 0
        self.save(update_fields=['otp_code', 'otp_created_at', 'otp_expires_at', 'otp_attempts'])
        return self.otp_code

    def verify_otp(self, code):
        if not self.otp_code or not self.otp_expires_at:
            return False, "No OTP requested"

        if timezone.now() > self.otp_expires_at:
            return False, "OTP has expired. Please request a new one."

        if self.otp_attempts >= 5:
            return False, "Too many attempts. Please request a new OTP."

        if self.otp_code == code:
            self.otp_code = None
            self.otp_expires_at = None
            self.otp_attempts = 0
            self.email_verified = True
            self.is_verified = True
            self.is_active = True
            self.user.is_active = True
            self.user.save(update_fields=['is_active'])
            self.save(update_fields=['otp_code', 'otp_expires_at', 'otp_attempts', 'email_verified', 'is_verified', 'is_active'])
            return True, "Verification successful!"
        else:
            self.otp_attempts += 1
            self.save(update_fields=['otp_attempts'])
            remaining = 5 - self.otp_attempts
            return False, f"Invalid OTP. {remaining} attempts remaining."

    def get_full_name(self):
        return self.user.get_full_name() or self.user.username

    def __str__(self):
        return f"{self.get_full_name()} - {self.title or 'Job Seeker'}"

    def get_absolute_url(self):
        return reverse('jobs:view_job_seeker_profile', kwargs={'pk': self.pk})


class TelegramProfile(models.Model):
    """Telegram bot integration profile."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='telegram_profile'
    )
    chat_id = models.BigIntegerField(unique=True, help_text="Telegram chat ID", db_index=True)
    username = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Telegram User: {self.user.username} (ID: {self.chat_id})"


class UserPreference(models.Model):
    """User preferences for language and currency."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='preferences'
    )
    language = models.CharField(
        max_length=10,
        choices=[('en', 'English'), ('am', 'አማርኛ')],
        default='en'
    )
    currency = models.CharField(
        max_length=3,
        choices=[('ETB', 'Birr'), ('USD', 'USD')],
        default='ETB'
    )

    class Meta:
        verbose_name = "User Preference"
        verbose_name_plural = "User Preferences"

    def __str__(self):
        return f"Preferences for {self.user.username}"


# ============================================================================
# JOB & BOOKING MODELS
# ============================================================================

class Job(models.Model):
    """Job posting with approval workflow."""
    EMPLOYMENT_TYPES = [
        ('Full-time', 'Full-time'),
        ('Part-time', 'Part-time'),
        ('Contract', 'Contract'),
        ('Freelance', 'Freelance'),
        ('Internship', 'Internship'),
    ]

    title = models.CharField(max_length=255, db_index=True)
    company_name = models.CharField(max_length=255, db_index=True)
    description = models.TextField()
    category = models.CharField(max_length=255, blank=True, db_index=True)
    employment_type = models.CharField(max_length=50, default='Full-time', choices=EMPLOYMENT_TYPES, db_index=True)

    experience_required = models.IntegerField(default=0, help_text="Experience in years")
    required_skills = models.ManyToManyField(Profession, related_name='job_requests', blank=True)

    location = models.CharField(max_length=255, db_index=True)
    preferred_schedule = models.CharField(max_length=255, blank=True, null=True)

    salary = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    budget = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    responsibilities = models.TextField(null=True, blank=True)
    description_of_work = models.TextField(blank=True, null=True)

    client = models.ForeignKey(ClientProfile, on_delete=models.CASCADE, related_name='jobs', null=True, blank=True)
    service_provider = models.ForeignKey(JobSeekerProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_jobs')

    posted_date = models.DateTimeField(auto_now_add=True, db_index=True)
    is_completed = models.BooleanField(default=False, db_index=True)
    is_approved = models.BooleanField(default=False, help_text="Admin approval required", db_index=True)
    approved_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-posted_date']
        verbose_name = "Job Posting"
        verbose_name_plural = "Job Postings"
        indexes = [
            models.Index(fields=['is_approved', 'is_completed']),
            models.Index(fields=['location', 'employment_type']),
        ]

    def __str__(self):
        return f"{self.title} at {self.company_name}"

    def get_absolute_url(self):
        return reverse('jobs:job_details', kwargs={'job_id': self.pk})


class Booking(models.Model):
    """Booking for a job with a service provider."""
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Confirmed', 'Confirmed'),
        ('In Progress', 'In Progress'),
        ('Completed', 'Completed'),
        ('Cancelled', 'Cancelled'),
    ]

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='bookings')
    service_provider = models.ForeignKey(JobSeekerProfile, on_delete=models.CASCADE, related_name='bookings')
    client = models.ForeignKey(ClientProfile, on_delete=models.CASCADE, related_name='bookings')
    start_date = models.DateTimeField(db_index=True)
    end_date = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='Pending', db_index=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['status', 'start_date'])]

    def __str__(self):
        return f"Booking: {self.job.title} - {self.service_provider.get_full_name()}"


# ============================================================================
# MESSAGING & REVIEWS
# ============================================================================

class Message(models.Model):
    """Direct message between users."""
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_messages')
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='received_messages')
    message = models.TextField()
    is_read = models.BooleanField(default=False, db_index=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [models.Index(fields=['sender', 'recipient'])]

    def __str__(self):
        return f"Message from {self.sender.username} to {self.recipient.username}"


class Review(models.Model):
    """Review/rating for a service provider."""
    RATING_CHOICES = [(i, str(i)) for i in range(1, 6)]

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='reviews')
    client = models.ForeignKey(ClientProfile, on_delete=models.CASCADE, related_name='reviews_given')
    service_provider = models.ForeignKey(JobSeekerProfile, on_delete=models.CASCADE, related_name='reviews_received')
    rating = models.PositiveIntegerField(choices=RATING_CHOICES, db_index=True)
    review_text = models.TextField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-timestamp']
        unique_together = ('job', 'client')

    def __str__(self):
        return f"Review for {self.service_provider.get_full_name()} - {self.rating}★"


class WorkerRating(models.Model):
    """Simple rating for a worker."""
    job_seeker = models.ForeignKey(JobSeekerProfile, on_delete=models.CASCADE, related_name='ratings')
    client = models.ForeignKey(ClientProfile, on_delete=models.CASCADE, related_name='ratings_given')
    rating = models.PositiveSmallIntegerField(choices=[(i, str(i)) for i in range(1, 6)], db_index=True)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('job_seeker', 'client')
        ordering = ['-created_at']

    def __str__(self):
        return f"Rating: {self.job_seeker.get_full_name()} - {self.rating}★"


# ============================================================================
# TALENT MARKETPLACE MODELS
# ============================================================================

class Talent(models.Model):
    """Pre-vetted talent for the marketplace."""
    name = models.CharField(max_length=100, db_index=True)
    role = models.CharField(max_length=100, db_index=True)
    location = models.CharField(max_length=100, db_index=True)
    bio = models.TextField()
    image = models.ImageField(upload_to='talents/', blank=True, null=True)

    category = models.CharField(max_length=50, db_index=True)
    experience = models.IntegerField(default=0)
    education = models.CharField(max_length=100, blank=True)
    skills = models.JSONField(default=list, blank=True)
    certifications = models.JSONField(default=list, blank=True)
    languages = models.JSONField(default=list, blank=True)

    price = models.IntegerField(db_index=True)
    duration = models.CharField(max_length=50)
    type = models.CharField(max_length=50, db_index=True)
    available_from = models.IntegerField(default=0, help_text="Days until available")
    availability = models.JSONField(default=list, blank=True)
    radius = models.IntegerField(default=0, help_text="Service radius in km")
    remote = models.BooleanField(default=False, db_index=True)

    rating = models.FloatField(default=0.0, db_index=True)
    reviews = models.IntegerField(default=0)
    sub_ratings = models.JSONField(default=dict, blank=True)
    portfolio = models.JSONField(default=list, blank=True)
    verified = models.BooleanField(default=False, db_index=True)
    top = models.BooleanField(default=False, db_index=True)
    tier = models.IntegerField(default=1, help_text="Verification tier (1-3)", db_index=True)

    created_at = models.DateField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    profile = models.OneToOneField(
        'JobSeekerProfile',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='talent'
    )

    class Meta:
        ordering = ['-rating', '-reviews']
        verbose_name_plural = 'Talents'
        indexes = [
            models.Index(fields=['category', 'verified', 'top']),
            models.Index(fields=['price', 'rating']),
        ]

    def __str__(self):
        return f"{self.name} - {self.role}"

    def get_contact_info(self):
        return {
            'email': f"{self.name.lower().replace(' ', '.')}@example.com",
            'phone': '+251 9XX XXX XXX',
        }


class HireRequest(models.Model):
    """Request to hire a specific talent."""
    talent = models.ForeignKey(Talent, on_delete=models.CASCADE, null=True, blank=True, related_name='hire_requests')
    company_name = models.CharField(max_length=200, db_index=True)
    email = models.EmailField()
    budget = models.IntegerField()
    details = models.TextField()
    status = models.CharField(max_length=20, choices=[
        ('Pending', 'Pending'), ('Reviewed', 'Reviewed'),
        ('Accepted', 'Accepted'), ('Rejected', 'Rejected')
    ], default='Pending', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        talent_name = self.talent.name if self.talent else 'Unknown'
        return f"Hire Request: {self.company_name} → {talent_name}"


class PostNeedRequest(models.Model):
    """Request posted by someone looking for talent."""
    job_title = models.CharField(max_length=200, db_index=True)
    description = models.TextField()
    budget = models.IntegerField()
    contact_email = models.EmailField(blank=True, null=True)
    contact_phone = models.CharField(max_length=20, blank=True, null=True)
    status = models.CharField(max_length=20, choices=[
        ('Open', 'Open'), ('In Progress', 'In Progress'),
        ('Filled', 'Filled'), ('Closed', 'Closed')
    ], default='Open', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Post Need Request'
        verbose_name_plural = 'Post Need Requests'
        indexes = [models.Index(fields=['status', 'created_at'])]

    def __str__(self):
        return self.job_title


# ============================================================================
# TALENT ACCESS (Payment‑gated contact)
# ============================================================================

class TalentAccess(models.Model):
    """Tracks payment status for viewing a talent's contact information."""
    employer = models.ForeignKey(ClientProfile, on_delete=models.CASCADE, related_name='talent_accesses')
    talent = models.ForeignKey(Talent, on_delete=models.CASCADE, related_name='accesses')
    paid = models.BooleanField(default=False, db_index=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('employer', 'talent')
        ordering = ['-created_at']
        verbose_name = "Talent Access"
        verbose_name_plural = "Talent Accesses"
        indexes = [models.Index(fields=['employer', 'paid'])]

    def __str__(self):
        status = "Paid" if self.paid else "Locked"
        return f"{self.employer.user.username} → {self.talent.name} ({status})"