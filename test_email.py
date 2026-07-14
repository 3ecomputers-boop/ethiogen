# test_email.py (create in project root)
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'job_portal.settings')
django.setup()

from django.core.mail import send_mail
from django.conf import settings

print(f"Email backend: {settings.EMAIL_BACKEND}")
print(f"Email host: {settings.EMAIL_HOST}")
print(f"Email port: {settings.EMAIL_PORT}")
print(f"Email user: {settings.EMAIL_HOST_USER}")
print(f"Email password: {'*' * len(settings.EMAIL_HOST_PASSWORD) if settings.EMAIL_HOST_PASSWORD else 'NOT SET'}")

try:
    send_mail(
        subject='Test Email',
        message='This is a test',
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=['your-test-email@example.com'],  # ← Change to your email
        fail_silently=False,
    )
    print("✅ Email sent successfully!")
except Exception as e:
    print(f"❌ Email failed: {e}")