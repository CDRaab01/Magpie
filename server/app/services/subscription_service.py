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
from app.models.merchant_tag import MerchantTag
from app.models.subscription_mute import SubscriptionMute
from app.models.transaction import COUNTABLE_STATUSES, Transaction
from app.rules.subscriptions import Recurrence, detect_recurrence

# Only merchants seen at least this many times are worth checking — a cheap SQL prefilter before
# the (still cheap) per-merchant detection.
_LOOKBACK_DAYS = 400

# The tag that unlocks Spotter's cost-per-visit decoration (Link G).
FITNESS_TAG = "fitness"


@dataclass(frozen=True)
class Subscription:
    merchant: str
    recurrence: Recurrence
    tags: frozenset[str] = frozenset()


def cost_per_visit_cents(annual_cost_cents: int, visits: int) -> int | None:
    """This subscription's monthly cost split across ``visits`` (Link G). None when ``visits`` is
    0 — you can't divide a cost by zero visits, and "0 visits" is the story anyway (paying, not
    going), carried separately by ``visits_this_month``."""
    if visits <= 0:
        return None
    return round((annual_cost_cents / 12) / visits)


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

    # Merchants the owner marked "not a subscription" (#12) — skipped for both the screen and the
    # sweeps, since every caller of this function goes through here.
    muted = {
        m
        for m in (
            await db.execute(
                select(SubscriptionMute.merchant).where(SubscriptionMute.user_id == user_id)
            )
        )
        .scalars()
        .all()
    }

    # Per-merchant tags (#Link G) — a merchant can hold several, so gather into a set per merchant.
    tags_by_merchant: dict[str, set[str]] = {}
    for merchant_name, tag in (
        await db.execute(
            select(MerchantTag.merchant, MerchantTag.tag).where(MerchantTag.user_id == user_id)
        )
    ).all():
        tags_by_merchant.setdefault(merchant_name, set()).add(tag)

    by_merchant: dict[str, list[tuple[datetime.date, int]]] = {}
    for name, date, amount in rows:
        if name and name.strip() and name not in muted:
            by_merchant.setdefault(name, []).append((date, amount))

    subs = []
    for name, dated_amounts in by_merchant.items():
        recurrence = detect_recurrence(dated_amounts)
        if recurrence is not None:
            subs.append(
                Subscription(
                    merchant=name,
                    recurrence=recurrence,
                    tags=frozenset(tags_by_merchant.get(name, ())),
                )
            )
    subs.sort(key=lambda s: -s.recurrence.annual_cost_cents)
    return subs
