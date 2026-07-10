"""Spending-anomaly detection (ROADMAP #19a) — pure, no I/O.

The proactive half of "watch my spending": the existing sweeps catch *known* deviations (a bill
that didn't come, a paycheck that was short); these catch the *novel* one — a big charge at a
merchant you've never used, or a category already over a normal month's spend partway through the
month. Deterministic thresholds only; any LLM narration (#19) is a line appended to the alert,
never the thing that fires it.

The "new merchant" and "recent" questions are DB/clock concerns the sweep owns; this module is
just the numeric judgments, so they are table-testable in isolation.
"""

from app.rules.bands import median_cents


def is_large_charge(amount_cents: int, threshold_cents: int) -> bool:
    """A spend whose magnitude meets the large-charge bar. Magnitude, so a refund's sign never
    reads as 'large'; the sweep additionally restricts this to `kind == "spend"`."""
    return abs(amount_cents) >= threshold_cents


def category_overspend(
    mtd_spend_cents: int,
    prior_full_month_spends: list[int],
    *,
    factor: float,
    floor_cents: int,
    min_months: int,
) -> float | None:
    """How far a category's month-to-date spend runs over `factor` × its trailing median, or None.

    `mtd_spend_cents` and `prior_full_month_spends` are magnitudes (positive = money out).
    Returns None unless there are at least `min_months` of prior full months (no median before
    that), the MTD spend clears the absolute `floor` (so a $5-median category spending $11 isn't
    "news"), and it exceeds `factor` × the trailing median. The overage returned is measured
    against the plain median, which is the honest "how much more than usual" number.
    """
    prior = [abs(a) for a in prior_full_month_spends]
    if len(prior) < min_months:
        return None
    mtd = abs(mtd_spend_cents)
    if mtd < floor_cents:
        return None
    median = median_cents(prior)
    if mtd <= median * factor:
        return None
    return mtd - median
