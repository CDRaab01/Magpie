"""Recurrence detection (ROADMAP #22) — pure, no I/O. Inverts the rules engine: instead of a rule
telling us a merchant recurs, we infer it from the transaction history. A merchant is
"subscription-shaped" when its charges land on a regular interval at a consistent amount — the
signal behind the recurrences screen, the new-recurrence alert, and the price-hike alert.
"""

import datetime
import statistics
from dataclasses import dataclass

from app.rules.bands import median_cents

# Interval buckets (days) a run of charges must cluster around to count as recurring.
_CADENCES = {
    "weekly": (6, 8),
    "biweekly": (12, 16),
    "monthly": (26, 35),
    "yearly": (350, 380),
}
_ANNUAL_MULTIPLIER = {"weekly": 52, "biweekly": 26, "monthly": 12, "yearly": 1}
MIN_OCCURRENCES = 3
AMOUNT_TOLERANCE = 0.20  # charges within ±20% of the median count as "the same" subscription
# A hike fires on a smaller jump than the detection tolerance: a real "$3 on $16" increase is
# ~19% — still "the same subscription" for grouping, but worth flagging. Tighter than
# AMOUNT_TOLERANCE by design, or every mild fluctuation inside the band would page.
PRICE_HIKE_TOLERANCE = 0.10


@dataclass(frozen=True)
class Recurrence:
    cadence: str
    typical_amount_cents: int  # median magnitude
    occurrences: int
    last_date: datetime.date
    last_amount_cents: int  # magnitude of the most recent charge
    annual_cost_cents: int


def detect_recurrence(
    dated_amounts: list[tuple[datetime.date, int]],
) -> Recurrence | None:
    """Infer a subscription from a merchant's (date, signed amount) history, or None.

    Requires ≥ `MIN_OCCURRENCES` charges whose gaps mostly match one cadence bucket and whose
    amounts sit within `AMOUNT_TOLERANCE` of their median. Amounts are magnitudes (a subscription
    is spend). The most recent charge is reported separately so callers can spot a price hike.
    """
    if len(dated_amounts) < MIN_OCCURRENCES:
        return None
    ordered = sorted(dated_amounts, key=lambda da: da[0])
    dates = [d for d, _ in ordered]
    amounts = [abs(a) for _, a in ordered]

    median = median_cents(amounts)
    if median <= 0:
        return None
    # Amount consistency: most charges near the median (one-off spikes don't disqualify a real sub).
    within = sum(1 for a in amounts if abs(a - median) <= median * AMOUNT_TOLERANCE)
    if within < MIN_OCCURRENCES:
        return None

    gaps = [(dates[i] - dates[i - 1]).days for i in range(1, len(dates))]
    typical_gap = statistics.median(gaps)
    cadence = next((c for c, (lo, hi) in _CADENCES.items() if lo <= typical_gap <= hi), None)
    if cadence is None:
        return None

    median_int = int(round(median))
    return Recurrence(
        cadence=cadence,
        typical_amount_cents=median_int,
        occurrences=len(ordered),
        last_date=dates[-1],
        last_amount_cents=amounts[-1],
        annual_cost_cents=median_int * _ANNUAL_MULTIPLIER[cadence],
    )


def price_hike_cents(recurrence: Recurrence) -> int | None:
    """How much the most recent charge exceeds the subscription's typical amount, or None if it's
    within tolerance. The price-hike signal ("Netflix went up $3")."""
    threshold = recurrence.typical_amount_cents * (1 + PRICE_HIKE_TOLERANCE)
    if recurrence.last_amount_cents <= threshold:
        return None
    return recurrence.last_amount_cents - recurrence.typical_amount_cents
