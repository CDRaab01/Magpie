import datetime
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.budget import Budget
from app.schemas.budget import BudgetCreate, BudgetOut, BudgetProposalOut, BudgetUpdate
from app.security import LedgerUser
from app.services.budget_service import (
    actual_spend_by_category,
    carry_forward_proposals,
    create_budget,
    list_budgets,
    propose_budgets,
    update_budget,
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
    current_user: LedgerUser,
    db: DbSession,
    month: Annotated[datetime.date, Query()],
):
    budgets = await list_budgets(db, current_user.id, month)
    actual = await actual_spend_by_category(db, current_user.id, month)
    return [_to_out(b, actual) for b in budgets]


@router.post("", response_model=BudgetOut, status_code=status.HTTP_201_CREATED)
async def create_new_budget(req: BudgetCreate, current_user: LedgerUser, db: DbSession):
    budget = await create_budget(db, current_user.id, req)
    actual = await actual_spend_by_category(db, current_user.id, budget.month)
    return _to_out(budget, actual)


@router.patch("/{budget_id}", response_model=BudgetOut)
async def patch_budget(
    budget_id: uuid.UUID, req: BudgetUpdate, current_user: LedgerUser, db: DbSession
):
    """Change a budget's monthly cap — how a coach cut draft is accepted, and plain manual edits."""
    budget = await update_budget(db, current_user.id, budget_id, req.amount)
    actual = await actual_spend_by_category(db, current_user.id, budget.month)
    return _to_out(budget, actual)


@router.get("/proposals", response_model=list[BudgetProposalOut])
async def budget_proposals(
    current_user: LedgerUser,
    db: DbSession,
    month: Annotated[datetime.date, Query()],
):
    """Suggested budgets from history (ROADMAP #20) — drafts the owner confirms one by one (each a
    POST /budgets), the review-not-enter law applied to budgets. Deterministic, not AI.

    Month rollover: when this month has no budgets yet, last month's budgets come back first as
    carry-forward drafts at their prior amounts (a new month never starts blind); otherwise the
    trailing-3-month median proposals for un-budgeted categories."""
    proposals = await carry_forward_proposals(db, current_user.id, month)
    if not proposals:
        proposals = await propose_budgets(db, current_user.id, month)
    return [
        BudgetProposalOut(category_id=cid, category_name=name, suggested_amount_cents=amount)
        for cid, name, amount in proposals
    ]
