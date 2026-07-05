"""Amount tolerance bands (CLAUDE.md §5) — pure, no I/O. A rolling median of matched
historical amounts ± a percentage tolerance, so a seasonal utility bill ("XCEL, monthly
±20%") doesn't get flagged every time it fluctuates within its normal range.
"""


def median_cents(amounts: list[int]) -> float:
    if not amounts:
        raise ValueError("Cannot compute a median of zero observations")
    ordered = sorted(amounts)
    n = len(ordered)
    mid = n // 2
    if n % 2 == 1:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2


def is_within_band(candidate_cents: int, historical_cents: list[int], pct: float) -> bool:
    """Compares magnitudes (abs value) — the sign is a `kind` concern (spend vs. income),
    not a band concern; a $45 bill and a -$45 bill are the same band question."""
    band_median = median_cents([abs(a) for a in historical_cents])
    tolerance = band_median * pct
    candidate = abs(candidate_cents)
    return (band_median - tolerance) <= candidate <= (band_median + tolerance)
