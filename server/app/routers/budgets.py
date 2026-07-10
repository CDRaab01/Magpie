import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.budget import Budget
from app.schemas.budget import BudgetCreate, BudgetOut, BudgetProposalOut
from app.security import CurrentUser
from app.services.budget_service import (
    actual_spend_by_category,
    create_budget,
    list_budgets,
    propose_budgets,
)

router = APIRouter(prefix="/budgets", tags=["budgets"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


def _to_out(budget: Budget, actual_by_category: dict) -> BudgetOut:
    return BudgetOut(
        id=budget.id,
        category_id=budget.category_id,
        month=budget.month,
        amount=budget.amount,
        actual_cents=actual_by_category.get(budget.category_id, 0),
    )


@router.get("", response_model=list[BudgetOut])
async def all_budgets(
    current_user: CurrentUser,
    db: DbSession,
    month: Annotated[datetime.date, Query()],
):
    budgets = await list_budgets(db, current_user.id, month)
    actual = await actual_spend_by_category(db, current_user.id, month)
    return [_to_out(b, actual) for b in budgets]


@router.post("", response_model=BudgetOut, status_code=status.HTTP_201_CREATED)
async def create_new_budget(req: BudgetCreate, current_user: CurrentUser, db: DbSession):
    budget = await create_budget(db, current_user.id, req)
    actual = await actual_spend_by_category(db, current_user.id, budget.month)
    return _to_out(budget, actual)


@router.get("/proposals", response_model=list[BudgetProposalOut])
async def budget_proposals(
    current_user: CurrentUser,
    db: DbSession,
    month: Annotated[datetime.date, Query()],
):
    """Suggested budgets from history (ROADMAP #20) — the trailing-3-month median per category,
    for categories without a budget yet this month. Drafts the owner confirms one by one (each a
    POST /budgets), the review-not-enter law applied to budgets. Deterministic, not AI."""
    proposals = await propose_budgets(db, current_user.id, month)
    return [
        BudgetProposalOut(category_id=cid, category_name=name, suggested_amount_cents=amount)
        for cid, name, amount in proposals
    ]
