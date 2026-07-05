"""Monthly cash-flow aggregation (CLAUDE.md §2, the Home "month in/out/net" panel).

Pure — takes a plain iterable of (kind, amount) pairs, no ORM/session dependency, so the
service layer maps rows into this shape and the math is testable without a database.
"""

from dataclasses import dataclass
from typing import Iterable, NamedTuple


class TransactionForRollup(NamedTuple):
    kind: str
    amount: int  # signed integer cents


@dataclass(frozen=True)
class MonthlyRollup:
    income_cents: int
    spend_cents: int  # signed (negative); refunds already netted in
    net_cents: int


def rollup_month(transactions: Iterable[TransactionForRollup]) -> MonthlyRollup:
    """Aggregate a set of transactions into income/spend/net.

    ``transfer`` transactions are excluded entirely — they're internal movement between the
    user's own accounts and must not inflate either total (CLAUDE.md §2 double-count trap).
    ``refund`` amounts are positive but summed alongside ``spend`` (not ``income``), so a
    refund nets its category's spend down without ever counting as income.
    """
    income_cents = 0
    spend_cents = 0
    for t in transactions:
        if t.kind == "income":
            income_cents += t.amount
        elif t.kind in ("spend", "refund"):
            spend_cents += t.amount
        elif t.kind == "transfer":
            continue
        else:
            raise ValueError(f"Unknown transaction kind: {t.kind!r}")

    return MonthlyRollup(
        income_cents=income_cents,
        spend_cents=spend_cents,
        net_cents=income_cents + spend_cents,
    )


class TransactionForCategoryRollup(NamedTuple):
    category_id: str | None
    kind: str
    amount: int  # signed integer cents


def rollup_by_category(
    transactions: Iterable[TransactionForCategoryRollup],
) -> dict[str | None, int]:
    """Month-vs-budget (CLAUDE.md Phase 7) needs spend *per category*, not just the
    household total — same kind rules as `rollup_month` (transfers excluded, refunds net
    spend down, never counted as income), grouped by `category_id` instead of summed flat."""
    totals: dict[str | None, int] = {}
    for t in transactions:
        if t.kind == "transfer" or t.kind == "income":
            continue
        if t.kind not in ("spend", "refund"):
            raise ValueError(f"Unknown transaction kind: {t.kind!r}")
        totals[t.category_id] = totals.get(t.category_id, 0) + t.amount
    return totals
