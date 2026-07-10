"""Budgets domain (CLAUDE.md §4/Phase 7): CRUD + month-vs-budget. Each `Budget` is scoped to its
owner via `user_id` (F10); "actual spend" is computed across every one of that user's accounts for
the category+month (a budget is a whole-household cap across the owner's accounts, not scoped by
account).
"""

import datetime
import uuid
from calendar import monthrange

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ledger.rollups import TransactionForCategoryRollup, rollup_by_category
from app.models.account import Account
from app.models.budget import Budget
from app.models.category import Category
from app.models.transaction import COUNTABLE_STATUSES, Transaction
from app.schemas.budget import BudgetCreate


async def _owned_category(db: AsyncSession, user_id: uuid.UUID, category_id: uuid.UUID) -> Category:
    result = await db.execute(
        select(Category).where(
            Category.id == category_id,
            or_(Category.user_id.is_(None), Category.user_id == user_id),
        )
    )
    category = result.scalar_one_or_none()
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    return category


async def create_budget(db: AsyncSession, user_id: uuid.UUID, req: BudgetCreate) -> Budget:
    await _owned_category(db, user_id, req.category_id)
    budget = Budget(
        user_id=user_id, category_id=req.category_id, month=req.month, amount=req.amount
    )
    db.add(budget)
    await db.commit()
    await db.refresh(budget)
    return budget


async def list_budgets(db: AsyncSession, user_id: uuid.UUID, month: datetime.date) -> list[Budget]:
    result = await db.execute(
        select(Budget).where(Budget.user_id == user_id, Budget.month == month)
    )
    return list(result.scalars().all())


async def actual_spend_by_category(
    db: AsyncSession, user_id: uuid.UUID, month: datetime.date
) -> dict[uuid.UUID, int]:
    """Every category's actual spend for the given month, across all of the user's accounts
    — keyed by category_id, so the caller can zip it against each Budget row."""
    start = month.replace(day=1)
    end = month.replace(day=monthrange(month.year, month.month)[1])
    result = await db.execute(
        select(Transaction)
        .join(Account, Transaction.account_id == Account.id)
        .where(
            Account.user_id == user_id,
            Transaction.date >= start,
            Transaction.date <= end,
            # A split parent is excluded here — its child parts carry the category breakdown, so
            # the split's spend lands in the right categories and isn't double-counted (#26).
            Transaction.is_split.is_(False),
            Transaction.status.in_(COUNTABLE_STATUSES),  # an expired auth hold is not spend
        )
    )
    rollup_input = (
        TransactionForCategoryRollup(t.category_id, t.kind, t.amount)
        for t in result.scalars().all()
        if t.category_id is not None
    )
    return rollup_by_category(rollup_input)


async def propose_budgets(
    db: AsyncSession, user_id: uuid.UUID, month: datetime.date
) -> list[tuple[uuid.UUID, str, int]]:
    """Suggested budgets from history (ROADMAP #20): the trailing-3-month median spend per
    category, for categories that don't already have a budget this month. Deterministic, not AI —
    the "review, not enter" law applied to budgets: these are drafts the owner confirms one by one.

    Returns (category_id, category_name, suggested_amount_cents), largest first. Median over the
    three *prior* full months (the target month is excluded — it may be partial), so a category
    needs at least one prior month of spend to be proposed.
    """
    from app.rules.bands import median_cents
    from sqlalchemy import func

    this_month = month.replace(day=1)
    total = this_month.year * 12 + (this_month.month - 1)
    window_start = datetime.date((total - 3) // 12, (total - 3) % 12 + 1, 1)

    month_bucket = func.date_trunc("month", Transaction.date)
    rows = (
        await db.execute(
            select(Transaction.category_id, month_bucket, func.sum(-Transaction.amount))
            .join(Account, Transaction.account_id == Account.id)
            .where(
                Account.user_id == user_id,
                Transaction.category_id.is_not(None),
                Transaction.kind.in_(("spend", "refund")),
                Transaction.is_split.is_(False),
                Transaction.status.in_(COUNTABLE_STATUSES),
                Transaction.date >= window_start,
                month_bucket < this_month,  # prior full months only
            )
            .group_by(Transaction.category_id, month_bucket)
        )
    ).all()

    already = {
        b.category_id
        for b in (
            await db.execute(
                select(Budget).where(Budget.user_id == user_id, Budget.month == this_month)
            )
        )
        .scalars()
        .all()
    }

    by_cat: dict[uuid.UUID, list[int]] = {}
    for cat_id, _bucket, spend in rows:
        by_cat.setdefault(cat_id, []).append(int(spend))

    names = {
        cid: name
        for cid, name in (
            await db.execute(
                select(Category.id, Category.name).where(
                    or_(Category.user_id == user_id, Category.user_id.is_(None))
                )
            )
        )
        .tuples()
        .all()
    }

    proposals = [
        (cid, names.get(cid, "Uncategorized"), int(round(median_cents([abs(a) for a in months]))))
        for cid, months in by_cat.items()
        if cid not in already and months
    ]
    proposals.sort(key=lambda p: -p[2])
    return [p for p in proposals if p[2] > 0]
