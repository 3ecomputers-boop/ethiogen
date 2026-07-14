# jobs/management/commands/sync_talents.py
from django.core.management.base import BaseCommand
from jobs.models import JobSeekerProfile
from jobs.signals import sync_talent_on_verification

class Command(BaseCommand):
    help = 'Create/update Talent records for all verified JobSeekerProfiles'

    def handle(self, *args, **options):
        profiles = JobSeekerProfile.objects.filter(is_verified=True, is_active=True)
        count = 0
        for profile in profiles:
            sync_talent_on_verification(sender=JobSeekerProfile, instance=profile, created=False)
            count += 1
            self.stdout.write(f"Processed {profile.user.username}")
        self.stdout.write(self.style.SUCCESS(f"Synced {count} profiles."))