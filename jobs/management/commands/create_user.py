from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()
from jobs.models import JobSeekerProfile, ClientProfile
from django_countries import countries


class Command(BaseCommand):
    help = 'Create a job seeker or client user without OTP verification'

    def add_arguments(self, parser):
        parser.add_argument('--type', type=str, choices=['seeker', 'client'], required=True,
                          help='Type of user to create')
        parser.add_argument('--username', type=str, required=True)
        parser.add_argument('--email', type=str, required=True)
        parser.add_argument('--password', type=str, required=True)
        parser.add_argument('--first-name', type=str, default='')
        parser.add_argument('--last-name', type=str, default='')
        parser.add_argument('--title', type=str, default='Professional')
        parser.add_argument('--company', type=str, default='')
        parser.add_argument('--country', type=str, default='ET', 
                          help='Country code (e.g., ET, US, GB)')
        parser.add_argument('--city', type=str, default='')

    def handle(self, *args, **options):
        user_type = options['type']
        username = options['username']
        email = options['email']
        password = options['password']
        
        # Check if user already exists
        if User.objects.filter(username=username).exists():
            self.stdout.write(
                self.style.ERROR(f'User "{username}" already exists!')
            )
            return
        
        # Create user
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=options['first_name'],
            last_name=options['last_name'],
            is_active=True  # Active immediately
        )
        
        # Create profile based on type
        if user_type == 'seeker':
            profile = JobSeekerProfile.objects.create(
                user=user,
                title=options['title'],
                country=options['country'],
                city=options['city'],
                is_verified=True,
                email_verified=True,
                is_active=True
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f'✓ Job seeker created: {username} ({email})\n'
                    f'  Title: {options["title"]}\n'
                    f'  Location: {options["city"]}, {options["country"]}\n'
                    f'  Status: Verified & Active (No OTP required)'
                )
            )
        
        elif user_type == 'client':
            profile = ClientProfile.objects.create(
                user=user,
                company_name=options['company'] or f"{options['first_name']}'s Company",
                location=f"{options['city']}, {options['country']}",
                is_verified=True
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f'✓ Client created: {username} ({email})\n'
                    f'  Company: {profile.company_name}\n'
                    f'  Location: {profile.location}\n'
                    f'  Status: Verified & Active (No OTP required)'
                )
            )