import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.cashflow import CashflowCalendarOut
from app.security import CurrentUser
from app.services.cashflow_service import get_cashflow_calendar

router = APIRouter(prefix="/cashflow", tags=["cashflow"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.get("", response_model=CashflowCalendarOut)
async def cashflow_calendar(current_user: CurrentUser, db: DbSession):
    """The "due before next paycheck" calendar (V1.md Tier 3 #23)."""
    now = datetime.datetime.now(datetime.timezone.utc)
    return await get_cashflow_calendar(db, current_user.id, now=now)
