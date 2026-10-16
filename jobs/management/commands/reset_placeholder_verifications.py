"""
Un-verify placeholder job-seeker profiles.

Background
----------
500 JobSeekerProfile rows were seeded from a list of Ethiopian profession
names. They carry a title but nothing else: almost no city, no country, no
skills, no bio, no rate. Yet 495 of them are flagged is_verified=True,
which makes the verification badge meaningless and, once tenant
dashboards exist, would show placeholder profiles as vetted talent.

A profile counts as a PLACEHOLDER when it has no city, no country, no
skills AND no bio. Anything with real detail keeps its current status.

This only ever sets is_verified True -> False. It never grants
verification, and it never touches ClientProfile (organisations) or the
User rows.

    python manage.py reset_placeholder_verifications          # dry run
    python manage.py reset_placeholder_verifications --apply  # do it

    By default this only touches the empty seeded shells. To also clear
    hand-registered profiles that still have some detail (use after
    reviewing them by hand):

    python manage.py reset_placeholder_verifications --include-detailed --apply
"""
from django.core.management.base import BaseCommand
from django.db.models import Q

from jobs.models import JobSeekerProfile


def placeholder_qs():
    return JobSeekerProfile.objects.filter(
        Q(city='') | Q(city__isnull=True),
        Q(country='') | Q(country__isnull=True),
    ).filter(
        Q(skills=[]) | Q(skills__isnull=True)
    ).filter(
        Q(bio='') | Q(bio__isnull=True)
    )


def detailed_qs():
    """The complement: anything with some real detail."""
    return JobSeekerProfile.objects.exclude(pk__in=placeholder_qs().values('pk'))


class Command(BaseCommand):
    help = 'Set is_verified=False on seeded placeholder job-seeker profiles.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='Actually write. Without this, nothing changes.')
        parser.add_argument('--include-detailed', action='store_true',
                            help='Also clear hand-registered profiles that have '
                                 'some real detail (city/country/skills/bio). '
                                 'Leaves nothing verified.')

    def handle(self, *args, **options):
        apply = options['apply']
        include_detailed = options['include_detailed']

        total = JobSeekerProfile.objects.count()
        placeholders = placeholder_qs()
        n_placeholder = placeholders.count()
        n_detailed = total - n_placeholder

        verified_total = JobSeekerProfile.objects.filter(is_verified=True).count()

        if include_detailed:
            target = JobSeekerProfile.objects.filter(is_verified=True)
            scope_note = 'EVERY verified profile'
        else:
            target = placeholders.filter(is_verified=True)
            scope_note = 'placeholder profiles only'

        self.stdout.write(self.style.HTTP_INFO('Placeholder verification reset'))
        self.stdout.write(f'  scope                     : {scope_note}')
        self.stdout.write(f'  JobSeekerProfile rows        : {total}')
        self.stdout.write(f'  look like placeholders        : {n_placeholder}')
        self.stdout.write(f'  have real detail (keep status): {n_detailed}')
        self.stdout.write(f'  currently marked verified    : {verified_total}')
        self.stdout.write(f'  would be set to NOT verified  : {target.count()}')
        self.stdout.write('')

        if target.count() == 0:
            self.stdout.write(self.style.WARNING('  Nothing to do.'))
            return

        self.stdout.write('  What WOULD change:')
        for profile in target.select_related('user')[:10]:
            self.stdout.write(
                f'      {profile.user.username[:32]:<32} '
                f'title={profile.title!r} city={profile.city!r} '
                f'skills={len(profile.skills or [])}'
            )
        remaining = target.count() - 10
        if remaining > 0:
            self.stdout.write(f'      ... and {remaining} more')
        self.stdout.write('')

        if not include_detailed:
            self.stdout.write('  Kept as-is (has real detail):')
            for profile in detailed_qs().select_related('user')[:8]:
                self.stdout.write(
                    f'      {profile.user.username[:32]:<32} '
                    f'title={profile.title!r} city={profile.city!r} '
                    f'country={str(profile.country)!r} verified={profile.is_verified}'
                )
            self.stdout.write('  (pass --include-detailed to clear these too)')

        if not apply:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING(
                '  DRY RUN. Re-run with --apply to make the change.'))
            return

        updated = target.update(is_verified=False)
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'  Set is_verified=False on {updated} profile(s).'))

        after = JobSeekerProfile.objects.filter(is_verified=True).count()
        self.stdout.write(f'  verified profiles now: {after} (was {verified_total})')
        self.stdout.write('  To reverse, re-set is_verified=True on those rows.')
