"""Read models for the analytics/chart surfaces (ROADMAP.md Wave 1). These are read-only
aggregations over the ledger — the heavy correctness lives in `app/ledger/` (pure), and these
functions just feed it DB rows, exactly as `transaction_service.monthly_summary` does for the
Home panel. `safe_to_spend` is deliberately a *composition* of two existing services (account
balances + the cash-flow projection) rather than new math — the genre's headline number is
just "balances minus what's due before payday"."""

import datetime
import uuid
from calendar import monthrange

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.ledger.rollups import (
    DatedForSeries,
    MonthlyRollupForMonth,
    TransactionForCategoryRollup,
    rollup_by_category,
    rollup_month_series,
)
from app.models.account import Account
from app.models.category import Category
from app.models.transaction import Transaction
from app.services.account_service import compute_account_balance
from app.services.cashflow_service import get_cashflow_calendar
from app.time_util import owner_local_date

UNCATEGORIZED_LABEL = "Uncategorized"


def _recent_months(today: datetime.date, count: int) -> list[tuple[int, int]]:
    """The `count` months ending with `today`'s month, oldest first — the x-axis of a trend
    chart. Walks calendar months (not 30-day windows) so the buckets line up with statements."""
    keys: list[tuple[int, int]] = []
    year, month = today.year, today.month
    for _ in range(count):
        keys.append((year, month))
        month -= 1
        if month == 0:
            month, year = 12, year - 1
    return list(reversed(keys))


def _month_bounds(month: datetime.date) -> tuple[datetime.date, datetime.date]:
    start = month.replace(day=1)
    end = month.replace(day=monthrange(month.year, month.month)[1])
    return start, end


async def spending_history(
    db: AsyncSession, user_id: uuid.UUID, *, months: int, now: datetime.datetime
) -> list[MonthlyRollupForMonth]:
    """The last `months` calendar months of income/spend/net (owner-local, F18)."""
    today = owner_local_date(now, settings.owner_timezone)
    month_keys = _recent_months(today, months)
    start = datetime.date(month_keys[0][0], month_keys[0][1], 1)

    result = await db.execute(
        select(Transaction.date, Transaction.kind, Transaction.amount)
        .join(Account, Transaction.account_id == Account.id)
        .where(
            Account.user_id == user_id,
            # Split children are internal allocations; the parent carries the full amount for
            # the household rollup (#26 — same rule as the Home month panel).
            Transaction.split_parent_id.is_(None),
            Transaction.date >= start,
        )
    )
    series = (
        DatedForSeries(year=d.year, month=d.month, kind=k, amount=a) for d, k, a in result.all()
    )
    return rollup_month_series(series, month_keys)


async def category_summary(
    db: AsyncSession, user_id: uuid.UUID, month: datetime.date
) -> list[tuple[uuid.UUID | None, str, int]]:
    """Net spend per category for the month, largest spend first. Returns
    (category_id, category_name, spend_cents); the uncategorized bucket has a None id."""
    start, end = _month_bounds(month)
    result = await db.execute(
        select(Transaction.category_id, Transaction.kind, Transaction.amount)
        .join(Account, Transaction.account_id == Account.id)
        .where(
            Account.user_id == user_id,
            Transaction.date >= start,
            Transaction.date <= end,
            # Split parents excluded; their parts carry the category breakdown (#26).
            Transaction.is_split.is_(False),
        )
    )
    totals = rollup_by_category(
        TransactionForCategoryRollup(cid, k, a) for cid, k, a in result.all()
    )

    names = await _category_names(db, user_id)
    items = [
        (
            cid,
            names.get(cid, UNCATEGORIZED_LABEL) if cid is not None else UNCATEGORIZED_LABEL,
            cents,
        )
        for cid, cents in totals.items()
    ]
    # Most negative (largest spend) first; refunds can push a category positive and sink to the end.
    items.sort(key=lambda i: i[2])
    return items


async def top_merchants(
    db: AsyncSession,
    user_id: uuid.UUID,
    month: datetime.date,
    *,
    category_id: uuid.UUID | None = None,
    limit: int = 10,
) -> list[tuple[str, int, int]]:
    """The drill-down below category: (merchant, spend_cents, count), largest spend first.
    Aggregated in SQL — this can span a whole backfill month, so it never loads rows into
    Python (F14 discipline)."""
    start, end = _month_bounds(month)
    # Ingested rows carry a normalized merchant (groups "SQ *COFFEE" with "COFFEE"); manual/CSV
    # rows may have only the raw name — coalesce so both participate and neither is dropped.
    merchant = func.coalesce(Transaction.merchant_norm, Transaction.merchant_raw)
    query = (
        select(
            merchant,
            func.sum(Transaction.amount),
            func.count(),
        )
        .join(Account, Transaction.account_id == Account.id)
        .where(
            Account.user_id == user_id,
            Transaction.date >= start,
            Transaction.date <= end,
            Transaction.is_split.is_(False),  # parts carry the category; parents are excluded
            Transaction.kind.in_(("spend", "refund")),  # spend view: income/transfers excluded
            merchant.is_not(None),
        )
        .group_by(merchant)
        .order_by(func.sum(Transaction.amount))  # most negative (biggest spend) first
        .limit(limit)
    )
    if category_id is not None:
        query = query.where(Transaction.category_id == category_id)
    result = await db.execute(query)
    return [(merchant, int(total), int(count)) for merchant, total, count in result.all()]


async def safe_to_spend(db: AsyncSession, user_id: uuid.UUID, *, now: datetime.datetime):
    """Depository balances minus the bills due before the next paycheck — the headline number.
    Cards are excluded: a card's balance is money owed, not money you have to spend."""
    accounts = (
        (
            await db.execute(
                select(Account).where(Account.user_id == user_id, Account.type == "depository")
            )
        )
        .scalars()
        .all()
    )
    depository_balance = 0
    for account in accounts:
        depository_balance += await compute_account_balance(db, account.id)

    calendar = await get_cashflow_calendar(db, user_id, now=now)
    due = calendar.total_due_before_paycheck_cents
    return {
        "safe_to_spend_cents": depository_balance - due,
        "depository_balance_cents": depository_balance,
        "due_before_paycheck_cents": due,
        "next_paycheck_date": calendar.next_paycheck_date,
    }


async def _category_names(db: AsyncSession, user_id: uuid.UUID) -> dict[uuid.UUID, str]:
    """Every category visible to the user (shared + own), id → name."""
    result = await db.execute(
        select(Category.id, Category.name).where(
            or_(Category.user_id.is_(None), Category.user_id == user_id)
        )
    )
    return {cid: name for cid, name in result.all()}
