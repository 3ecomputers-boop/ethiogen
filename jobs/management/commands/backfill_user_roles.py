"""
Create the Role rows and backfill accounts.User.role.

Background
----------
The Role table was empty, so every one of the 510 users had role=NULL and
accounts.User.is_employer / .is_job_seeker both returned falsy for
everybody. That quietly breaks anything branching on role.

Precedence, highest first:

    is_superuser            -> super_admin
    is_staff                -> admin
    has a ClientProfile     -> employer
    has a JobSeekerProfile  -> job_seeker
    otherwise               -> left NULL (no profile yet)

A user with both a ClientProfile and a JobSeekerProfile is recorded as an
employer: the organisational role is the one that grants access to the
private workspace.

    python manage.py backfill_user_roles          # dry run
    python manage.py backfill_user_roles --apply  # write
    python manage.py backfill_user_roles --apply --with-permissions
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import Role
from jobs.models import ClientProfile, JobSeekerProfile

ROLE_SPECS = [
    ('super_admin', 'Full platform administration: tenants, billing, users.'),
    ('admin', 'Staff administration without platform-wide access.'),
    ('employer', 'An organisation: post jobs, review applicants, manage a team.'),
    ('job_seeker', 'An individual worker in the public marketplace.'),
]

# Opt-in baseline, only applied with --with-permissions.
# Deliberately read-only: nothing here grants write access to another
# organisation's records.
VIEW_ONLY_MODELS = [
    ('jobs', 'jobpost'),
    ('jobs', 'jobapplication'),
    ('jobs', 'clientprofile'),
    ('jobs', 'jobseekerprofile'),
    ('jobs', 'category'),
    ('jobs', 'subcategory'),
    ('billing', 'channelpost'),
    ('billing', 'subscription'),
]


class Command(BaseCommand):
    help = 'Create Role rows and assign accounts.User.role from existing profiles.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='Actually write. Without this, nothing changes.')
        parser.add_argument('--with-permissions', action='store_true',
                            help='Also attach a read-only permission baseline '
                                 'to each role.')

    def handle(self, *args, **options):
        apply = options['apply']
        User = get_user_model()

        # --- ensure the roles exist (safe to re-run) ---------------------
        existing = {r.name for r in Role.objects.all()}
        missing = [(n, d) for n, d in ROLE_SPECS if n not in existing]
        if missing:
            for name, description in missing:
                Role.objects.get_or_create(
                    name=name, defaults={'description': description})
            self.stdout.write(
                f'  created {len(missing)} role(s): '
                f'{", ".join(n for n, _ in missing)}'
            )
        else:
            self.stdout.write('  all 4 roles already exist')
        self.stdout.write('')

        roles = {r.name: r for r in Role.objects.all()}

        # --- work out each user's role -----------------------------------
        client_ids = set(ClientProfile.objects.values_list('user_id', flat=True))
        seeker_ids = set(JobSeekerProfile.objects.values_list('user_id', flat=True))

        plan = {'super_admin': [], 'admin': [], 'employer': [],
                'job_seeker': [], None: []}
        for user in User.objects.all().order_by('id'):
            if user.is_superuser:
                plan['super_admin'].append(user)
            elif user.is_staff:
                plan['admin'].append(user)
            elif user.id in client_ids:
                plan['employer'].append(user)
            elif user.id in seeker_ids:
                plan['job_seeker'].append(user)
            else:
                plan[None].append(user)

        self.stdout.write(self.style.HTTP_INFO('Role plan'))
        for name in ('super_admin', 'admin', 'employer', 'job_seeker', None):
            label = name or 'no role (left NULL)'
            self.stdout.write(f'  {label:<24} {len(plan[name])}')
        self.stdout.write(f'  {"total":<24} {User.objects.count()}')
        self.stdout.write('')

        # Only users that would actually change.
        changes = []
        for name, users in plan.items():
            if name is None:
                continue
            for user in users:
                if user.role_id != roles[name].id:
                    changes.append((user, roles[name]))

        self.stdout.write(f'  users whose role will change: {len(changes)}')
        already = User.objects.exclude(role=None).count()
        self.stdout.write(f'  users already holding a role : {already}')
        self.stdout.write('')

        if plan[None]:
            self.stdout.write('  Left as NULL (no profile, not staff):')
            for user in plan[None][:10]:
                self.stdout.write(f'      {user.username[:36]:<36} '
                                  f'staff={user.is_staff}')
            self.stdout.write('      (these can be assigned once they register '
                              'a profile)')
            self.stdout.write('')

        both = client_ids & seeker_ids
        if both:
            self.stdout.write('  Users with BOTH profiles, assigned to employer:')
            for uid in both:
                self.stdout.write(f'      {User.objects.get(pk=uid).username}')
            self.stdout.write('')

        if not apply:
            self.stdout.write(self.style.WARNING('  DRY RUN. Re-run with --apply.'))
            return

        with transaction.atomic():
            for user, role in changes:
                User.objects.filter(pk=user.pk).update(role=role)
        self.stdout.write(self.style.SUCCESS(
            f'  Assigned roles on {len(changes)} user(s).'))

        # Report the result
        after = {}
        for user in User.objects.all():
            key = user.role.name if user.role else None
            after[key] = after.get(key, 0) + 1
        self.stdout.write('  roles now:')
        for name, n in sorted(after.items(), key=lambda kv: -(kv[1] or 0)):
            self.stdout.write(f'      {name or "NULL":<16} {n}')

        if options['with_permissions']:
            self._assign_permissions(roles)

    def _assign_permissions(self, roles):
        """Attach a read-only permission baseline to each role."""
        self.stdout.write('')
        self.stdout.write(self.style.HTTP_INFO('Permission baseline (read-only)'))
        by_codename = {}
        for codename, app_label, model in Permission.objects.values_list(
                'codename', 'content_type__app_label', 'content_type__model'):
            by_codename.setdefault((app_label, model), []).append(codename)

        baseline = []
        for app_label, model in VIEW_ONLY_MODELS:
            for codename in by_codename.get((app_label, model), []):
                if codename.startswith('view_'):
                    baseline.append(codename)

        self.stdout.write(f'  {len(baseline)} view permission(s) found')
        for name in ('job_seeker', 'employer', 'admin', 'super_admin'):
            role = roles[name]
            added = role.permissions.add(*baseline)
            self.stdout.write(f'      {name:<12} +{added}')
        self.stdout.write(self.style.WARNING(
            '  This grants READ access only. No add/change/delete was granted.'))
