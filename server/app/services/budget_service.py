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
from app.models.transaction import Transaction
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
        )
    )
    rollup_input = (
        TransactionForCategoryRollup(t.category_id, t.kind, t.amount)
        for t in result.scalars().all()
        if t.category_id is not None
    )
    return rollup_by_category(rollup_input)
