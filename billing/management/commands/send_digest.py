"""
Send the daily digest to subscribers who chose that mode.

Run from cron once an hour, e.g.

    0 * * * * cd /path/to/project && venv/bin/python manage.py send_digest

Subscribers are grouped by their chosen hour, so a subscriber who asked for
08:00 gets one message at 08:00 (server local time).
"""
import time

from django.core.management.base import BaseCommand

from billing.alerts import active_alert_subscriptions, send_digests
from billing.models import Subscription


class Command(BaseCommand):
    help = 'Send the daily job digest to subscribers in that mode.'

    def add_arguments(self, parser):
        parser.add_argument('--hour', type=int, default=None,
                            help='Only send to subscribers with this digest hour. '
                                 'Default: all hours due now.')
        parser.add_argument('--dry-run', action='store_true',
                            help='Report what would be sent without sending.')
        parser.add_argument('--lookback', type=int, default=24,
                            help='How many hours back to include (default 24).')
        parser.add_argument('--all-hours', action='store_true',
                            help='Ignore stored hours and digest everyone now. '
                                 'Useful right after changing the schedule.')

    def handle(self, *args, **options):
        hour = options['hour']
        if options['all_hours']:
            hour = None

        total_active = active_alert_subscriptions().count()
        digest_subs = active_alert_subscriptions().filter(
            alert_mode=Subscription.ALERT_DIGEST
        ).count()

        self.stdout.write(
            f'Active subscribers: {total_active}  '
            f'(digest mode: {digest_subs})'
        )

        if digest_subs == 0:
            self.stdout.write('  nobody is on digest mode, nothing to do')
            return

        result = send_digests(
            hour=hour,
            dry_run=options['dry_run'],
            lookback_hours=options['lookback'],
        )
        prefix = '[dry run] ' if options['dry_run'] else ''
        self.stdout.write(
            f'{prefix}digests sent={result["sent"]} '
            f'failed={result["failed"]} '
            f'no_new_posts={result["no_new_posts"]} '
            f'(posts in window: {result["posts_in_window"]})'
        )
        if result['failed']:
            self.stdout.write(self.style.WARNING(
                'Some digests failed. Check the bot token and the users\' chat ids.'))
