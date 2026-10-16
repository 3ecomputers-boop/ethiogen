"""
Seed or publish ProfessionalRate rows.

  manage.py seed_professional_rates                 seed the table if empty
  manage.py seed_professional_rates --week 2026-10-19
                                                   publish a new week
                                                   (copies the current rates
                                                   forward and shifts the week on)
  manage.py seed_professional_rates --reset         overwrite from the seed table

Rates are held per week so an admin can publish next week's prices without
disturbing the week currently advertised. --week copies the current rows
forward, which is the normal way to roll a new week.
"""
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction

from jobs.models import ProfessionalRate, current_week_rates
from jobs.rates import ORDER, WORKER_WAGES, client_rate, rate_card

DAYS_PER_WEEK = 6


def monday_of(d):
    return d - timedelta(days=d.weekday())


class Command(BaseCommand):
    help = "Seed or publish weekly professional rates."

    def add_arguments(self, parser):
        parser.add_argument(
            "--week", metavar="YYYY-MM-DD",
            help="Monday that starts the week to publish. Copies the current "
                 "rates forward and moves them onto this date.",
        )
        parser.add_argument(
            "--reset", action="store_true",
            help="Overwrite existing rows from the built-in seed table.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        week = options["week"]
        if week:
            week = monday_of(date.fromisoformat(week))
        else:
            week = monday_of(date.today())

        existing = ProfessionalRate.objects.count()

        if options["reset"]:
            ProfessionalRate.objects.all().delete()
            existing = 0
            self.stdout.write(self.style.WARNING("Deleted all existing rates (--reset)."))

        # -- publish a new week from what is currently live ------------------
        if week and existing:
            current = current_week_rates()
            if current:
                created = 0
                for row in current:
                    ProfessionalRate.objects.create(
                        profession=row.profession,
                        worker_wage_daily=row.worker_wage_daily,
                        client_rate_daily=row.client_rate_daily,
                        effective_from=week,
                        working_days_per_week=row.working_days_per_week,
                        sort_order=row.sort_order,
                        note=row.note,
                        is_active=True,
                    )
                    created += 1
                self.stdout.write(self.style.SUCCESS(
                    "Published %d rate(s) for the week of %s." % (created, week)))
                self._report()
                return

        # -- seed from the built-in table ------------------------------------
        # client_rate_daily is deliberately left NULL so it derives from the
        # worker wage. Storing it would pin the rate, and an admin editing the
        # wage afterwards would see the client rate stubbornly not move --
        # which defeats the markup rule the whole card is built on.
        created = 0
        for row in rate_card():
            _obj, was_created = ProfessionalRate.objects.update_or_create(
                profession=row["profession"],
                defaults={
                    "worker_wage_daily": row["worker_wage_daily"],
                    "client_rate_daily": None,
                    "effective_from": week,
                    "working_days_per_week": DAYS_PER_WEEK,
                    "sort_order": row["sort_order"],
                    "is_active": True,
                },
            )
            created += int(was_created)

        self.stdout.write(self.style.SUCCESS(
            "Week of %s: %d rate(s) present (%d newly created)."
            % (week, ProfessionalRate.objects.filter(effective_from=week).count(), created)))
        self._report()

    def _report(self):
        self.stdout.write("")
        self.stdout.write("%-28s %-12s %-13s %s"
                          % ("profession", "worker/day", "client/day", "client/week"))
        self.stdout.write("-" * 72)
        for row in current_week_rates():
            self.stdout.write("%-28s %-12s %-13s %s" % (
                row.profession[:27],
                row.worker_wage_daily,
                row.effective_client_rate_daily(),
                "{:,}".format(row.weekly_client_rate()),
            ))
        self.stdout.write("-" * 72)
        self.stdout.write("Edit these under Jobs -> Professional rates in the admin.")
