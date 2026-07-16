import dataclasses
import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.insight import MonthlyInsightOut
from app.security import LedgerUser
from app.services.ingest_service import make_llm_client
from app.services.insight_service import generate_monthly_insight

router = APIRouter(prefix="/insights", tags=["insights"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.get("/monthly", response_model=MonthlyInsightOut)
async def monthly_insight(
    current_user: LedgerUser,
    db: DbSession,
    month: Annotated[datetime.date, Query()],
    narrative: Annotated[bool, Query()] = True,
):
    """The month's deterministic "what changed" aggregate, plus a best-effort LLM narrative
    (ROADMAP #18). The figures are always present; `narrative_source` is `"llm"` when the local
    model produced prose and `"unavailable"` when it is off or didn't respond. Any day in the
    month works — it is normalized to the first.

    `narrative=false` skips the LLM entirely and returns the aggregate only — the fast path the
    Home insight card uses, so opening Home never waits on a model call."""
    llm_client = make_llm_client() if narrative else None
    insight = await generate_monthly_insight(db, current_user.id, month, llm_client=llm_client)
    return MonthlyInsightOut(**dataclasses.asdict(insight))
