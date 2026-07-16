import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.security import LedgerUser
from app.services.export_service import export_month_csv

router = APIRouter(prefix="/export", tags=["export"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.get("/transactions.csv", response_class=PlainTextResponse)
async def export_transactions(
    current_user: LedgerUser,
    db: DbSession,
    month: Annotated[datetime.date, Query()],
):
    """One month's ledger as CSV (ROADMAP #26) — the trust/escape-hatch feature that keeps the
    data the owner's. Any day in the month works; it's normalized to the first. A
    Content-Disposition header names the file so a client share/save gets a sensible filename."""
    csv_text = await export_month_csv(db, current_user.id, month)
    filename = f"magpie-{month:%Y-%m}.csv"
    return PlainTextResponse(
        csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
