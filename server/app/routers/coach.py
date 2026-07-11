"""AI budget coach endpoints (owner-requested, 2026-07-11): goal CRUD, month-progress status over
the full budget table, per-category analysis, and the savings plan. Everything returned here is
deterministic in Stage 1 (`narrative_source="unavailable"`); Stage 3 layers the LLM narrative on
via `?narrative=true`. Plans and statuses are never persisted — accepting a coach suggestion is
the owner writing a budget (POST/PATCH /budgets), the drafts-never-auto-commit law (§6)."""

import datetime
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.coach import CategoryAnalysisOut, CoachPlanOut, CoachStatusOut, GoalOut, GoalUpsert
from app.security import CurrentUser
from app.services.coach_service import (
    build_category_analysis,
    build_coach_status,
    build_savings_plan,
    clear_goal,
    get_goal,
    upsert_goal,
)

router = APIRouter(prefix="/coach", tags=["coach"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


@router.get("/status", response_model=CoachStatusOut)
async def coach_status(
    current_user: CurrentUser,
    db: DbSession,
    narrative: Annotated[bool, Query()] = False,
):
    """Where the month stands: every budgeted category's pace + vs-usual context (the full table),
    the net projection, the goal delta, and the uncategorized blind-spot figure."""
    status_out = await build_coach_status(db, current_user.id, now=_now())
    # Stage 3 wires `narrative=true` to ai/coach.narrate_coach; until then it's a no-op.
    return status_out


@router.get("/plan", response_model=CoachPlanOut)
async def coach_plan(
    current_user: CurrentUser,
    db: DbSession,
    monthly_savings_cents: Annotated[int | None, Query(gt=0)] = None,
    narrative: Annotated[bool, Query()] = False,
):
    """ "What would need to change" to hit a monthly savings target — computed, never stored.
    Defaults to the active goal's amount; 400 when neither a target nor a goal exists."""
    target = monthly_savings_cents
    if target is None:
        goal = await get_goal(db, current_user.id)
        if goal is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "No savings target: pass monthly_savings_cents or set a goal first.",
            )
        target = goal.amount_cents
    return await build_savings_plan(db, current_user.id, target, now=_now())


@router.get("/category/{category_id}", response_model=CategoryAnalysisOut)
async def coach_category(
    category_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
    narrative: Annotated[bool, Query()] = False,
):
    """One category in depth — trend, vs-usual, budget history, top merchants this month."""
    return await build_category_analysis(db, current_user.id, category_id, now=_now())


@router.get("/goal", response_model=GoalOut | None)
async def read_goal(current_user: CurrentUser, db: DbSession):
    goal = await get_goal(db, current_user.id)
    if goal is None:
        return None
    return GoalOut(
        id=goal.id, kind=goal.kind, amount_cents=goal.amount_cents, created_at=goal.created_at
    )


@router.put("/goal", response_model=GoalOut)
async def set_goal(req: GoalUpsert, current_user: CurrentUser, db: DbSession):
    """Set (or change) the monthly savings goal — one active goal, updated in place."""
    goal = await upsert_goal(db, current_user.id, req.amount_cents)
    return GoalOut(
        id=goal.id, kind=goal.kind, amount_cents=goal.amount_cents, created_at=goal.created_at
    )


@router.delete("/goal", status_code=status.HTTP_204_NO_CONTENT)
async def remove_goal(current_user: CurrentUser, db: DbSession):
    await clear_goal(db, current_user.id)
