"""Subscription surfacing (ROADMAP #22): the recurrences the ledger already contains, totaled and
sorted by annual cost — "your recurring charges, what they cost you a year". Detection is pure
(`app/rules/subscriptions.py`); this gathers each merchant's spend history and runs it.

The per-merchant history is aggregated in SQL to (date, amount) pairs — cheap even over a
backfill (F14): a subscription is a handful of rows per merchant, not a table scan into Python.
"""

import datetime
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.transaction import COUNTABLE_STATUSES, Transaction
from app.rules.subscriptions import Recurrence, detect_recurrence

# Only merchants seen at least this many times are worth checking — a cheap SQL prefilter before
# the (still cheap) per-merchant detection.
_LOOKBACK_DAYS = 400


@dataclass(frozen=True)
class Subscription:
    merchant: str
    recurrence: Recurrence


async def list_subscriptions(
    db: AsyncSession, user_id: uuid.UUID, *, now: datetime.datetime
) -> list[Subscription]:
    """Every subscription-shaped merchant, richest (highest annual cost) first."""
    since = now.date() - datetime.timedelta(days=_LOOKBACK_DAYS)
    merchant = func.coalesce(Transaction.merchant_norm, Transaction.merchant_raw)
    rows = (
        await db.execute(
            select(merchant, Transaction.date, Transaction.amount)
            .join(Account, Transaction.account_id == Account.id)
            .where(
                Account.user_id == user_id,
                Transaction.kind == "spend",
                Transaction.split_parent_id.is_(None),
                Transaction.status.in_(COUNTABLE_STATUSES),
                Transaction.date >= since,
                merchant.is_not(None),
            )
            .order_by(merchant, Transaction.date)
        )
    ).all()

    by_merchant: dict[str, list[tuple[datetime.date, int]]] = {}
    for name, date, amount in rows:
        if name and name.strip():
            by_merchant.setdefault(name, []).append((date, amount))

    subs = []
    for name, dated_amounts in by_merchant.items():
        recurrence = detect_recurrence(dated_amounts)
        if recurrence is not None:
            subs.append(Subscription(merchant=name, recurrence=recurrence))
    subs.sort(key=lambda s: -s.recurrence.annual_cost_cents)
    return subs
