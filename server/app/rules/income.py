"""Recurring-income detection (ROADMAP #1) — pure, no I/O. Infers a paycheck/rent-shaped income
stream from a merchant's deposit history, so the owner can confirm it into a `recurring_income`
rule that arms paycheck-late/short, next-paycheck-date, and safe-to-spend.

Distinct from subscription detection on purpose: a paycheck's *timing* is regular but its *amount
swings* (overtime, bonuses — BAE runs ~44% variance in the real ledger), so the amount tolerance
is looser and the band is derived from the data rather than fixed. The recency gate (a former
employer whose last deposit is old must not become a live "late paycheck" alert) is the caller's
job — it needs the clock — but the shape here carries `last_date` so the caller can apply it.
"""

import datetime
import statistics
from dataclasses import dataclass

from app.rules.bands import median_cents

# Cadence buckets (median gap in days) → recurrence kind + a slack window for paycheck-late.
_CADENCES = {
    "weekly": ((6, 8), 2),
    "biweekly": ((12, 16), 4),
    "monthly": ((26, 35), 5),
}
MIN_OCCURRENCES = 4  # a paycheck stream needs a few observations before a cadence is trustworthy
# A paycheck's amount varies, but not chaotically: reject a stream whose robust spread exceeds this
# fraction of its median (person-to-person Venmo/Zelle is chaotic and lands here, a paycheck doesn't).
MAX_SPREAD = 0.55
BAND_MIN_PCT = 0.15  # never propose a band tighter than this — even a steady paycheck flexes
BAND_MAX_PCT = 0.40  # nor wider than this — beyond it, "short" loses meaning


@dataclass(frozen=True)
class IncomeShape:
    cadence: str
    slack_days: int
    typical_amount_cents: int  # median magnitude
    band_pct: float  # data-derived amount tolerance for the recurring_income rule
    occurrences: int
    last_date: datetime.date


def _robust_spread(amounts: list[int], median: float) -> float:
    """MAD/median — a robust coefficient of variation. Robust so a single bonus check doesn't
    inflate it the way a plain stddev would."""
    if median <= 0:
        return 1.0
    mad = statistics.median([abs(a - median) for a in amounts])
    return mad / median


def detect_income(dated_amounts: list[tuple[datetime.date, int]]) -> IncomeShape | None:
    """Infer a recurring-income shape from a merchant's (date, signed amount) deposits, or None.

    Requires ≥ MIN_OCCURRENCES deposits landing on a regular cadence with a not-too-chaotic amount.
    The band is derived from the observed spread (clamped), so a variable paycheck gets a wide band
    and a steady rent gets a tight one. Amounts are magnitudes (income is positive by convention,
    but abs() keeps it robust either way).
    """
    if len(dated_amounts) < MIN_OCCURRENCES:
        return None
    ordered = sorted(dated_amounts, key=lambda da: da[0])
    dates = [d for d, _ in ordered]
    amounts = [abs(a) for _, a in ordered]

    median = median_cents(amounts)
    if median <= 0:
        return None
    spread = _robust_spread(amounts, median)
    if spread > MAX_SPREAD:
        return None  # too chaotic to be a paycheck/rent (person-to-person transfers land here)

    gaps = [(dates[i] - dates[i - 1]).days for i in range(1, len(dates))]
    typical_gap = statistics.median(gaps)
    match = next(
        ((c, slack) for c, ((lo, hi), slack) in _CADENCES.items() if lo <= typical_gap <= hi),
        None,
    )
    if match is None:
        return None
    cadence, slack = match

    band_pct = min(BAND_MAX_PCT, max(BAND_MIN_PCT, round(spread * 1.5, 2)))
    return IncomeShape(
        cadence=cadence,
        slack_days=slack,
        typical_amount_cents=int(round(median)),
        band_pct=band_pct,
        occurrences=len(ordered),
        last_date=dates[-1],
    )
