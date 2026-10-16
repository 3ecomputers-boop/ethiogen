"""
Published price list for construction trades.

This module holds the arithmetic and the seed data. The live prices live in the
database (jobs.ProfessionalRate) so they can be edited from Django admin
without a deploy, and jobs/models.py imports PLATFORM_MARKUP from here.

Rates are in ETB per working day. `client` is not hand-entered: every published
client rate is exactly 1.25x the worker's daily wage, so it is derived from
MARKUP rather than stored. That keeps the margin consistent if a wage is ever
revised -- the hand-maintained table had 750 -> 938, which is 937.5 rounded, so
stored values had already drifted from the rule.

Adding a trade is one line in WORKER_WAGES; the client rate follows.
"""

# Markup applied to the worker's daily wage to get the client rate.
PLATFORM_MARKUP = MARKUP = 1.25

# Trade -> worker wage in ETB/day.
WORKER_WAGES = {
    "General labourer": 500,
    "Mason": 800,
    "Carpenter": 800,
    "Steel fixer": 800,
    "Plasterer": 750,
    "Painter": 700,
    "Electrician": 1000,
    "Plumber": 1000,
    "Welder": 1000,
    "Heavy equipment operator": 1500,
    "Foreman": 1500,
    "Site supervisor": 1800,
}

# Display order for the public rate card, grouped by pay band.
ORDER = [
    "General labourer",
    "Painter",
    "Plasterer",
    "Mason",
    "Carpenter",
    "Steel fixer",
    "Electrician",
    "Plumber",
    "Welder",
    "Heavy equipment operator",
    "Foreman",
    "Site supervisor",
]


def client_rate(worker_wage):
    """Client rate for a worker wage, rounded to the nearest whole birr."""
    return int(round(worker_wage * MARKUP))


def rate_card():
    """
    Seed rows for jobs.ProfessionalRate, in display order.

    Used by the seed management command and as a fallback for the public menu
    when the table is empty. Prices live in the database in normal operation.
    """
    return [
        {
            "profession": name,
            "worker_wage_daily": WORKER_WAGES[name],
            "client_rate_daily": client_rate(WORKER_WAGES[name]),
            "sort_order": index,
        }
        for index, name in enumerate(ORDER)
    ]


def worker_wage_for(category):
    """Worker wage for a trade name, case/format tolerant. None if unknown."""
    if not category:
        return None
    key = " ".join(str(category).split()).strip().lower()
    for name, wage in WORKER_WAGES.items():
        if name.lower() == key:
            return wage
    return None


def hire_rate_for(category):
    """
    What a client pays per day to hire this trade, or None if unknown.

    This -- not the worker wage -- is what a public listing is priced at, since
    a listing is quoted to the client. Prefers the live database row so an
    admin edit is reflected immediately; falls back to the seed table.
    """
    if not category:
        return None
    try:
        from .models import ProfessionalRate
    except Exception:
        return None

    name = None
    key = " ".join(str(category).split()).strip().lower()
    for row in ProfessionalRate.objects.filter(is_active=True):
        if row.profession.strip().lower() == key:
            name = row.profession
            break
    if name is None:
        wage = worker_wage_for(key)
        return None if wage is None else client_rate(wage)

    row = ProfessionalRate.objects.filter(
        profession=name, is_active=True).order_by('-effective_from').first()
    return row.effective_client_rate_daily() if row else None


# ---------------------------------------------------------------------------
# Duration multipliers, used to turn a daily rate into a listing price.
#
# Talent.price is a total paired with Talent.duration, and the seeded data was
# incoherent against it -- a Plumber advertised at 12,000 ETB "Daily" is 10x
# the published rate. These multipliers keep a listing consistent with the
# published card whatever period it is sold over.
# ---------------------------------------------------------------------------
HOURS_PER_DAY = 8
DAYS_PER_WEEK = 6          # construction standard, Sunday off
WEEKS_PER_MONTH = 26
MONTHS_PER_YEAR = 12

DURATION_MULTIPLIERS = {
    "hourly": 1.0 / HOURS_PER_DAY,
    "daily": 1.0,
    "weekly": float(DAYS_PER_WEEK),
    "monthly": float(WEEKS_PER_MONTH),
    "annually": float(WEEKS_PER_MONTH * MONTHS_PER_YEAR),
}

# Durations that cannot be derived from a daily rate, so a listing priced over
# one of these is left untouched rather than guessed at.
NON_DERIVABLE = {"project", "special units"}


def listing_price(daily_rate, duration):
    """Total price for a daily rate over a period, or None if not derivable."""
    if not daily_rate or not duration:
        return None
    key = str(duration).strip().lower()
    if key in NON_DERIVABLE:
        return None
    mult = DURATION_MULTIPLIERS.get(key)
    if mult is None:
        return None
    return int(round(daily_rate * mult))
