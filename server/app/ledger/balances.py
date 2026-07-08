"""Per-account balance (CLAUDE.md §9 — the Accounts screen's ledger-vs-statement delta).

Deliberately distinct from `rollups.py`'s household-wide monthly rollup: a household rollup
excludes `transfer` transactions entirely (they're internal movement between the user's own
accounts and must not inflate income/spend), but an individual ACCOUNT's own balance must
include every transfer leg that touched it — money genuinely left or entered that specific
account. Summing all kinds (spend/income/refund/transfer) for one account is exactly right.

**Balance is computed *between* checkpoints (CLAUDE.md §4 — the F1 fix).** The ledger does not
hold an account's full lifetime from $0, so summing every transaction ever and comparing to a
statement's stated balance is meaningless: after a 12-month backfill the derived total is a
*net change*, not an absolute balance, and the account would read "off by X" forever (X = the
balance at the start of the backfill), making the statement-parity gate unreachable.

Instead we *anchor*: the earliest `statement_checkpoint`'s stated balance is a known-true
absolute balance, and every transaction dated after it accrues on top. Transactions dated
on/before the anchor are already baked into that stated balance, so they're excluded — which
is exactly why prior history the ledger never saw doesn't matter. The honesty meter (the
delta) then checks whether the ledger fully accounts for the movement *between* the earliest
and latest checkpoints; it's meaningful only once a second checkpoint exists (a single
checkpoint reconciles to zero trivially, because the account is anchored to it).
"""

from dataclasses import dataclass
from datetime import date as date_
from typing import Iterable, NamedTuple


class DatedAmount(NamedTuple):
    """A transaction reduced to what balance math needs: its date and its signed integer cents.
    The date drives the checkpoint window; the amount is summed regardless of kind."""

    date: date_
    amount: int


@dataclass(frozen=True)
class CheckpointAnchor:
    """A balance anchor derived from a `statement_checkpoint`: the institution's stated balance
    *as of* the statement's closing date. The stated balance already reflects every transaction
    dated on/before ``statement_date``."""

    statement_date: date_
    stated_cents: int


def derived_balance(
    transactions: Iterable[DatedAmount], anchor: CheckpointAnchor | None = None
) -> int:
    """The account's current derived balance.

    With an ``anchor`` (the *earliest* checkpoint), start from its stated balance and add every
    transaction dated strictly after it — transactions on/before the anchor date are already
    inside the stated balance. Without an anchor (an account never reconciled against a
    statement), fall back to the plain signed sum of all transactions, transfers included.
    """
    if anchor is None:
        return sum(t.amount for t in transactions)
    return anchor.stated_cents + sum(
        t.amount for t in transactions if t.date > anchor.statement_date
    )


def reconciliation_delta(
    transactions: Iterable[DatedAmount],
    earliest: CheckpointAnchor | None,
    latest: CheckpointAnchor | None,
) -> int | None:
    """Ledger-vs-statement delta — the app's honesty meter (CLAUDE.md §9), computed *at* the
    latest checkpoint.

    Anchor at the earliest checkpoint's stated balance, add the transactions in the
    ``(earliest, latest]`` window, and compare to the latest checkpoint's stated balance. Zero
    means the ledger fully accounts for the money that moved between the two anchors. ``None``
    when the account has no checkpoint yet to compare against.

    A single checkpoint (``earliest is latest``) reconciles to zero: the window is empty and
    the derived value equals the stated one — the account is simply anchored to it, and the
    delta only becomes a real signal once a second statement gives it something to check
    against.
    """
    if earliest is None or latest is None:
        return None
    derived_at_latest = earliest.stated_cents + sum(
        t.amount for t in transactions if earliest.statement_date < t.date <= latest.statement_date
    )
    return derived_at_latest - latest.stated_cents
