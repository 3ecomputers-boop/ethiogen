"""
Reconcile Talent.price with the published rate card.

Talent.price is a total paired with Talent.duration, and the seeded data was
incoherent against it -- a Plumber advertised at 12,000 ETB "Daily" is roughly
10x the published 1,250/day rate, while trades of equal skill sat at 1,500 and
18,000.

Only listings whose trade maps unambiguously to the rate card AND that already
carry a price are touched. Deliberately NOT touched:

  * records priced 0 -- these are unpriced category placeholders (467 of the
    513 are Amharic trade names), and inventing a price for them would assert
    a rate the operator never agreed to;
  * non-trade professionals (Architect, Professor, Data Scientist, Marketer,
    consultants, developers) -- the rate card covers construction trades and
    says nothing about them;
  * Project / Special Units durations, which cannot be derived from a daily
    rate without inventing a scope.

Defaults to a dry run. Pass --apply to write.
"""
from collections import Counter

from django.core.management.base import BaseCommand
from django.db.models import Count

from jobs.models import Talent
from jobs.rates import WORKER_WAGES, hire_rate_for, listing_price

# role spelling on Talent -> trade name in jobs.rates.WORKER_WAGES.
# Only unambiguous synonyms; anything ambiguous is left alone and reported.
ROLE_ALIASES = {
    "electrician": "Electrician",
    "electrician & wiring": "Electrician",
    "electrical": "Electrician",
    "plumber": "Plumber",
    "site supervisor": "Site supervisor",
    "heavy machine operator": "Heavy equipment operator",
    "foreman": "Foreman",
    "forman": "Foreman",          # common misspelling in the seeded data
    "mason": "Mason",
    "carpenter": "Carpenter",
    "welder": "Welder",
    "steel fixer": "Steel fixer",
    "plasterer": "Plasterer",
    "painter": "Painter",
}


def trade_for(role):
    key = " ".join(str(role or "").split()).strip().lower()
    if key in ROLE_ALIASES:
        return ROLE_ALIASES[key]
    # fall back to an exact match against the card itself
    for name in WORKER_WAGES:
        if name.lower() == key:
            return name
    return None


class Command(BaseCommand):
    help = "Reconcile Talent.price with the published rate card (dry run by default)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Write the changes. Without this flag nothing is modified.",
        )

    def handle(self, *args, **options):
        apply = options["apply"]
        mode = "APPLY" if apply else "DRY RUN (pass --apply to write)"

        self.stdout.write("")
        self.stdout.write("Reconciling Talent.price with the published rate card")
        self.stdout.write("Mode: %s" % mode)
        self.stdout.write("-" * 78)

        fixes = []
        skipped_no_card = Counter()
        skipped_zero_price = 0
        skipped_not_derivable = Counter()

        qs = (
            Talent.objects.values("id", "name", "role", "duration", "price")
            .annotate(n=Count("id"))
            .order_by("role")
        )

        for row in qs:
            role = row["role"]
            price = row["price"] or 0
            duration = row["duration"]

            if price <= 0:
                skipped_zero_price += row["n"]
                continue

            trade = trade_for(role)
            if trade is None:
                skipped_no_card[str(role)[:34]] += row["n"]
                continue

            # A listing is quoted to the client, so it is priced off the
            # client rate (worker wage x markup), not the worker's take-home.
            daily = hire_rate_for(trade)
            new_price = listing_price(daily, duration)
            if new_price is None:
                skipped_not_derivable[str(duration)] += row["n"]
                continue

            if new_price != price:
                fixes.append((row["id"], row["n"], role, trade, duration, price, new_price))

        if not fixes:
            self.stdout.write("No priced listing deviates from the rate card.")
        else:
            self.stdout.write(
                "%-5s %-6s %-24s %-14s %-12s %s"
                % ("id", "n", "role", "duration", "current", "corrected")
            )
            self.stdout.write("-" * 78)
            for pk, n, role, trade, duration, old, new in fixes:
                self.stdout.write(
                    "%-5s %-6s %-24s %-14s %-12s %s   (%s)"
                    % (pk, n, str(role)[:23], str(duration)[:13], old, new, trade)
                )
            self.stdout.write("-" * 78)
            self.stdout.write("%d listing group(s), %d record(s) to change"
                              % (len(fixes), sum(f[1] for f in fixes)))

        self.stdout.write("")
        self.stdout.write("Left untouched:")
        self.stdout.write("  %d record(s) priced 0 (unpriced category placeholders)"
                          % skipped_zero_price)
        if skipped_no_card:
            self.stdout.write("  priced listings whose trade is not on the card "
                              "(professionals, not construction trades):")
            for role, n in skipped_no_card.most_common():
                self.stdout.write("      %-36s x%d" % (role, n))
        if skipped_not_derivable:
            self.stdout.write("  priced listings whose duration cannot be derived "
                              "from a daily rate:")
            for dur, n in skipped_not_derivable.most_common():
                self.stdout.write("      %-36s x%d" % (dur, n))

        if not apply or not fixes:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING("Dry run: nothing written."))
            return

        changed = 0
        for pk, n, _role, _trade, _dur, _old, new in fixes:
            changed += Talent.objects.filter(pk=pk).update(price=new)
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Updated %d record(s)." % changed))
