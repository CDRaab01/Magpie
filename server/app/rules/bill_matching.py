"""Bill-to-payment matching (CLAUDE.md §4/§10) — pure, no I/O. A `bill_issued` event (a
biller's "statement ready" notice) is matched to the later payment transaction on the same
account, within a window after the due date (payments often land a few days either side).
"""

import datetime
from dataclasses import dataclass


@dataclass(frozen=True)
class BillCandidate:
    id: str
    account_id: str
    amount_due: int
    due_date: datetime.date


@dataclass(frozen=True)
class PaymentCandidate:
    id: str
    account_id: str
    amount_cents: int
    date: datetime.date


def find_bill_payment(
    bill: BillCandidate,
    pool: list[PaymentCandidate],
    window_days: int = 10,
) -> PaymentCandidate | None:
    """The closest-dated payment on the *same* account (a bill's payment rail, CLAUDE.md §2)
    whose magnitude matches the amount due, within `window_days` of the due date either side.
    Exact-amount only — a partial payment is a real thing but out of scope for this heuristic
    and falls through to "unmatched"."""
    lo = bill.due_date - datetime.timedelta(days=window_days)
    hi = bill.due_date + datetime.timedelta(days=window_days)
    best: PaymentCandidate | None = None
    best_gap: int | None = None
    for candidate in pool:
        if candidate.account_id != bill.account_id:
            continue
        if abs(candidate.amount_cents) != abs(bill.amount_due):
            continue
        if not (lo <= candidate.date <= hi):
            continue
        gap = abs((candidate.date - bill.due_date).days)
        if best is None or gap < best_gap:
            best, best_gap = candidate, gap
    return best


def is_bill_missing(
    bill_due_date: datetime.date, today: datetime.date, grace_days: int = 3
) -> bool:
    """A bill is "missing" once its due date plus a small grace window has passed with no
    matched payment — the caller checks `matched_transaction_id is None` before calling this;
    this function only answers the time question."""
    return today > bill_due_date + datetime.timedelta(days=grace_days)
