"""Transfer-pair matching (CLAUDE.md §2/§5) — pure, no I/O. A card payment is two
transactions that must net to zero across *different* accounts (the double-count trap this
whole design exists to avoid): an outflow from checking, an inflow on the card. This finds
the best candidate partner for a new transaction out of a pool the caller has already fetched
from the DB (same account-scoping the caller already applies elsewhere).
"""

import datetime
from dataclasses import dataclass


@dataclass(frozen=True)
class TransferCandidate:
    id: str
    account_id: str
    amount_cents: int
    date: datetime.date


def find_transfer_match(
    candidate: TransferCandidate,
    pool: list[TransferCandidate],
    window_days: int = 3,
) -> TransferCandidate | None:
    """The closest-dated pool member on a *different* account whose amount exactly cancels
    the candidate's, within `window_days` either side (a payment can post to checking a day
    or two before/after it posts to the card). Exact cancellation only — partial payments
    are a real thing but out of scope for this heuristic; they fall through to review."""
    lo = candidate.date - datetime.timedelta(days=window_days)
    hi = candidate.date + datetime.timedelta(days=window_days)
    best: TransferCandidate | None = None
    best_gap: int | None = None
    for other in pool:
        if other.account_id == candidate.account_id:
            continue
        if other.amount_cents != -candidate.amount_cents:
            continue
        if not (lo <= other.date <= hi):
            continue
        gap = abs((other.date - candidate.date).days)
        if best is None or gap < best_gap:
            best, best_gap = other, gap
    return best
