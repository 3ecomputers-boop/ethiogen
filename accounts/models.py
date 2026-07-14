from django.contrib.auth.models import AbstractUser
from django.db import models

ROLE_CHOICES = [
    ('super_admin', 'Super Admin'),
    ('admin', 'Admin'),
    ('employer', 'Employer'),
    ('job_seeker', 'Job Seeker'),
]


class Role(models.Model):
    """Model representing a user role with specific permissions."""
    
    name = models.CharField(
        max_length=50, 
        choices=ROLE_CHOICES, 
        unique=True,
        verbose_name="Role Name"
    )
    description = models.TextField(
        blank=True, 
        verbose_name="Description"
    )
    permissions = models.ManyToManyField(
        'auth.Permission', 
        blank=True, 
        related_name='roles',
        verbose_name="Permissions"
    )
    created_at = models.DateTimeField(
        auto_now_add=True, 
        verbose_name="Created At"
    )

    class Meta:
        ordering = ['name']
        verbose_name = "Role"
        verbose_name_plural = "Roles"

    def __str__(self):
        return self.get_name_display()


class User(AbstractUser):
    """Custom User model extending Django's default AbstractUser."""
    
    role = models.ForeignKey(
        Role, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='users',
        verbose_name="Role"
    )
    is_verified = models.BooleanField(
        default=False, 
        verbose_name="Is Verified"
    )
    is_suspended = models.BooleanField(
        default=False, 
        verbose_name="Is Suspended"
    )
    suspension_reason = models.TextField(
        blank=True, 
        verbose_name="Suspension Reason"
    )
    last_login_ip = models.GenericIPAddressField(
        null=True, 
        blank=True, 
        verbose_name="Last Login IP"
    )

    class Meta:
        ordering = ['-date_joined']
        verbose_name = "User"
        verbose_name_plural = "Users"

    def __str__(self):
        role_display = self.role.get_name_display() if self.role else "No Role"
        return f"{self.username} ({role_display})"

    @property
    def is_employer(self):
        """Check if the user has the employer role."""
        return self.role and self.role.name == 'employer'

    @property
    def is_job_seeker(self):
        """Check if the user has the job seeker role."""
        return self.role and self.role.name == 'job_seeker'