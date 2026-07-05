"""Per-account balance (CLAUDE.md §9 — the Accounts screen's ledger-vs-statement delta).

Deliberately distinct from `rollups.py`'s household-wide monthly rollup: a household rollup
excludes `transfer` transactions entirely (they're internal movement between the user's own
accounts and must not inflate income/spend), but an individual ACCOUNT's own balance must
include every transfer leg that touched it — money genuinely left or entered that specific
account. Summing all kinds (spend/income/refund/transfer) for one account is exactly right.
"""

from dataclasses import dataclass
from typing import Iterable, NamedTuple


class TransactionForBalance(NamedTuple):
    amount: int  # signed integer cents


def account_balance(transactions: Iterable[TransactionForBalance]) -> int:
    """The account's derived balance: the sum of every transaction's signed amount,
    regardless of kind (unlike the household rollup, transfers are NOT excluded here)."""
    return sum(t.amount for t in transactions)


@dataclass(frozen=True)
class BalanceCheckpoint:
    computed_cents: int
    stated_cents: int | None  # None when no statement_checkpoint exists yet for this account


def balance_delta(checkpoint: BalanceCheckpoint) -> int | None:
    """Ledger-vs-statement delta — the app's honesty meter (CLAUDE.md §9). None when there's
    no checkpoint yet to compare against (a brand-new account, or one never reconciled)."""
    if checkpoint.stated_cents is None:
        return None
    return checkpoint.computed_cents - checkpoint.stated_cents
