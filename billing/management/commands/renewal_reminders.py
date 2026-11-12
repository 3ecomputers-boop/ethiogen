"""
Send renewal reminders for subscriptions expiring soon, and mark expired ones.

    python manage.py renewal_reminders            # remind (3 days) + expire
    python manage.py renewal_reminders --days 7   # remind 7 days out
    python manage.py renewal_reminders --dry-run  # report only
"""
from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from billing import services
from billing.models import Subscription


class Command(BaseCommand):
    help = 'Remind subscribers whose plan is expiring, and expire lapsed ones.'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=3,
                            help='Remind when expiry is within this many days.')
        parser.add_argument('--dry-run', action='store_true',
                            help='Report only; send nothing.')

    def handle(self, *args, **options):
        days = options['days']
        dry = options['dry_run']
        now = timezone.now()
        horizon = now + timedelta(days=days)

        # --- 1. expire lapsed subscriptions ------------------------------
        lapsed = Subscription.objects.filter(
            status=Subscription.STATUS_ACTIVE,
            expires_at__isnull=False,
            expires_at__lt=now,
        )
        expired_count = 0
        for sub in lapsed:
            if not dry:
                sub.status = Subscription.STATUS_EXPIRED
                sub.save(update_fields=['status', 'updated_at'])
            expired_count += 1
        self.stdout.write(f'Expired {expired_count} lapsed subscription(s).')

        # --- 2. remind soon-to-expire ones -------------------------------
        soon = Subscription.objects.filter(
            status=Subscription.STATUS_ACTIVE,
            expires_at__isnull=False,
            expires_at__gte=now,
            expires_at__lte=horizon,
        ).select_related('user')

        reminded = 0
        for sub in soon:
            if dry:
                reminded += 1
                continue
            chat_id = sub.telegram_chat_id or services.resolve_chat_id(sub.user)
            if chat_id:
                services.send_to_user(
                    chat_id,
                    "\u23F0 *Your Ethiogen subscription is expiring soon*\n\n"
                    f"Plan: *{sub.plan_name}*\n"
                    f"Expires: {timezone.localtime(sub.expires_at):%d %b %Y}\n\n"
                    "Renew now to keep applying to jobs and tenders in the channel.",
                    parse_mode='Markdown',
                )
            if sub.user.email:
                from billing import emails

                emails.send(
                    sub.user.email,
                    'Your Ethiogen subscription is expiring soon',
                    f'Hi {sub.user.first_name or "there"},\n\n'
                    f'Your {sub.plan_name} subscription expires on '
                    f'{timezone.localtime(sub.expires_at):%d %b %Y}.\n\n'
                    f'Renew to keep applying: {services.target_chat_id() and "https://t.me/ethiogenjob"}\n',
                )
            reminded += 1

        self.stdout.write(
            self.style.SUCCESS(f'Reminded {reminded} subscriber(s) (window {days} days).')
        )