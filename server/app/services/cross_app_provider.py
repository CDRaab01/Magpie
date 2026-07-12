"""Magpie's cross-app PROVIDER surface (federated awareness Link D, CROSS-APP.md rule 7).

`GET /cross-app/summary?start=&end=` gives a sister app the household's money shape for a window —
income/spend/net + grocery spend + the savings-goal target. Consumed by Cookbook's grocery tile
("planned vs spent"), and the digest-useful basics ride along.

Aggregates only, by construction (§6): whole-dollar sums, never a transaction row. Read-only.
"""

import datetime
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.category import Category
from app.models.transaction import COUNTABLE_STATUSES, Transaction
from app.services.coach_service import get_goal

# The Magpie category a grocery tile maps to. Shared category, matched case-insensitively so
# "Groceries"/"Grocery" both count; a household without one just reports 0.
GROCERY_CATEGORY_LIKE = "grocer%"


async def build_summary(
    db: AsyncSession, user_id: uuid.UUID, start: datetime.date, end: datetime.date
) -> dict:
    """Income/spend/net + grocery spend over [start, end], whole dollars. Transfers excluded and
    split parents only (household-rollup discipline, #26); spend/grocery reported as positive."""
    # Income and spend magnitudes over the window (transfers are internal movement, excluded).
    kind_rows = (
        await db.execute(
            select(Transaction.kind, func.coalesce(func.sum(Transaction.amount), 0))
            .join(Account, Transaction.account_id == Account.id)
            .where(
                Account.user_id == user_id,
                Transaction.split_parent_id.is_(None),
                Transaction.status.in_(COUNTABLE_STATUSES),
                Transaction.kind.in_(("income", "spend", "refund")),
                Transaction.date >= start,
                Transaction.date <= end,
            )
            .group_by(Transaction.kind)
        )
    ).all()
    by_kind = {k: int(v) for k, v in kind_rows}
    income = max(0, by_kind.get("income", 0))
    # spend + refund are stored negative; net them and report as a positive magnitude.
    spend = abs(by_kind.get("spend", 0) + by_kind.get("refund", 0))

    grocery = int(
        await db.scalar(
            select(func.coalesce(func.sum(-Transaction.amount), 0))
            .join(Account, Transaction.account_id == Account.id)
            .join(Category, Transaction.category_id == Category.id)
            .where(
                Account.user_id == user_id,
                Transaction.split_parent_id.is_(None),
                Transaction.status.in_(COUNTABLE_STATUSES),
                Transaction.kind.in_(("spend", "refund")),
                Category.name.ilike(GROCERY_CATEGORY_LIKE),
                Transaction.date >= start,
                Transaction.date <= end,
            )
        )
        or 0
    )

    goal = await get_goal(db, user_id)
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "income": round(income / 100),
        "spend": round(spend / 100),
        "net": round((income - spend) / 100),
        "grocery_spend": round(max(0, grocery) / 100),
        "savings_goal": (
            {"monthly_target": round(goal.amount_cents / 100)} if goal is not None else None
        ),
    }
