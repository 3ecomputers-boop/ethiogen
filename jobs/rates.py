"""
Published rate card for construction trades.

Single source of truth for the daily rates shown on the public rate card and
used to price talent listings. Rates are in ETB per working day.

`client` is not hand-entered: every published client rate in the card is
exactly 1.25x the worker's daily wage, so it is derived from MARKUP rather
than stored. That keeps the margin consistent if a wage is ever revised -- the
old table had 750 -> 938, which is 937.5 rounded, so hand-maintained values
had already drifted from the rule.

Adding a trade is one line in WORKER_WAGES; the client rate follows.
"""

# Markup applied to the worker's daily wage to get the client rate.
MARKUP = 1.25

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
    """The public rate card, in display order."""
    return [
        {
            "category": name,
            "worker_wage": WORKER_WAGES[name],
            "client_rate": client_rate(WORKER_WAGES[name]),
        }
        for name in ORDER
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
    a listing is quoted to the client.
    """
    wage = worker_wage_for(category)
    return None if wage is None else client_rate(wage)


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
