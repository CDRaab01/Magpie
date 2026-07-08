"""Pending→posted reconciliation (F4) — pure, no I/O.

An email alert captures a swipe as a `pending` transaction the moment it happens; the monthly
CSV/OFX reconciliation later imports the same swipe as a `posted` row. Left alone these are two
rows for one swipe — and because the email row stays `pending` forever while the CSV row is
`posted`, both count in the Home rollup, double-counting every reconciled swipe. The fix is to
*merge*: when a CSV row is the same swipe as an existing pending email row, promote that one
row to posted instead of creating a second.

This module is just the matcher: given a posted CSV row and the account's pending email
candidates, pick the one that is the same swipe within a tip/date tolerance. The caller does the
promotion and owns the DB.
"""

from dataclasses import dataclass
from datetime import date as date_


@dataclass(frozen=True)
class PendingCandidate:
    id: str
    amount_cents: int  # signed
    date: date_


def find_pending_match(
    amount_cents: int,
    txn_date: date_,
    candidates: list[PendingCandidate],
    *,
    window_days: int = 3,
    tip_pct: float = 0.30,
) -> PendingCandidate | None:
    """The pending candidate that is the same swipe as this posted CSV row, or None.

    A match must be the same direction (a spend can't reconcile a deposit), dated within
    ``window_days`` (a swipe posts a day or two after the alert), and the same magnitude *or*
    grown by up to ``tip_pct`` — a restaurant pre-auth alerts at the pre-tip amount and settles
    higher, so the posted magnitude is ≥ the pending one. A pre-auth that settles *lower* is the
    auth-hold-expiry domain, not this. Ties break on closest date, then smallest amount gap.
    """
    best: PendingCandidate | None = None
    best_key: tuple[int, int] | None = None
    for c in candidates:
        if (amount_cents > 0) != (c.amount_cents > 0):
            continue  # opposite directions are never the same swipe
        day_gap = abs((c.date - txn_date).days)
        if day_gap > window_days:
            continue
        posted, pending = abs(amount_cents), abs(c.amount_cents)
        exact = posted == pending
        tipped = posted > pending and posted <= round(pending * (1 + tip_pct))
        if not (exact or tipped):
            continue
        key = (day_gap, posted - pending)
        if best is None or key < best_key:
            best, best_key = c, key
    return best
