import dataclasses
import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.insight import MonthlyInsightOut
from app.security import CurrentUser
from app.services.ingest_service import make_llm_client
from app.services.insight_service import generate_monthly_insight

router = APIRouter(prefix="/insights", tags=["insights"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.get("/monthly", response_model=MonthlyInsightOut)
async def monthly_insight(
    current_user: CurrentUser,
    db: DbSession,
    month: Annotated[datetime.date, Query()],
):
    """The month's deterministic "what changed" aggregate, plus a best-effort LLM narrative
    (ROADMAP #18). The figures are always present; `narrative_source` is `"llm"` when the local
    model produced prose and `"unavailable"` when it is off or didn't respond. Any day in the
    month works — it is normalized to the first."""
    insight = await generate_monthly_insight(
        db, current_user.id, month, llm_client=make_llm_client()
    )
    return MonthlyInsightOut(**dataclasses.asdict(insight))
