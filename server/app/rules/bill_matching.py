"""Bill-to-payment matching (CLAUDE.md §4/§10) — pure, no I/O. A `bill_issued` event (a
biller's "statement ready" notice) is matched to the later payment transaction on the same
account, within a window after the due date (payments often land a few days either side).
"""

import datetime
from dataclasses import dataclass

DEFAULT_WINDOW_DAYS = 10

# F13: only money *leaving* the payment rail can settle a bill. `income` and `refund` are
# inflows by the sign convention; a `transfer` qualifies because paying a card statement from
# checking is a transfer leg (CLAUDE.md §2), and its outflow leg is the one that pays the bill.
BILL_PAYMENT_KINDS = ("spend", "transfer")


@dataclass(frozen=True)
class BillCandidate:
    id: str
    account_id: str
    amount_due: int  # positive — the amount owed
    due_date: datetime.date


@dataclass(frozen=True)
class PaymentCandidate:
    id: str
    account_id: str
    amount_cents: int  # signed: outflows are negative
    date: datetime.date
    kind: str  # one of TRANSACTION_KINDS


def find_bill_payment(
    bill: BillCandidate,
    pool: list[PaymentCandidate],
    window_days: int = DEFAULT_WINDOW_DAYS,
    exclude_transaction_ids: frozenset[str] = frozenset(),
) -> PaymentCandidate | None:
    """The closest-dated payment on the *same* account (a bill's payment rail, CLAUDE.md §2)
    whose magnitude matches the amount due, within `window_days` of the due date either side.
    Exact-amount only — a partial payment is a real thing but out of scope for this heuristic
    and falls through to "unmatched".

    F13, the two guards that make this safe:

    * **Direction.** The old matcher compared `abs(amount)` alone, so a $150 *deposit* landing
      near a $150 bill's due date "paid" it — the bill went quiet and the missing-bill alert
      never fired. A payment must be an outflow (`amount_cents < 0`) of a payment-shaped kind.
    * **One bill per transaction.** A transaction already claimed by another bill is excluded,
      so two same-amount bills on one rail can't both point at the single payment that settled
      only one of them. The caller supplies the claimed set; a partial unique index on
      `bill_statements.matched_transaction_id` is the durable backstop.
    """
    lo = bill.due_date - datetime.timedelta(days=window_days)
    hi = bill.due_date + datetime.timedelta(days=window_days)
    best: PaymentCandidate | None = None
    best_gap: int | None = None
    for candidate in pool:
        if candidate.id in exclude_transaction_ids:
            continue
        if candidate.account_id != bill.account_id:
            continue
        if candidate.kind not in BILL_PAYMENT_KINDS:
            continue
        if candidate.amount_cents >= 0:
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
