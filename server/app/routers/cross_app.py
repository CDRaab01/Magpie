"""Magpie's cross-app PROVIDER surface (federated awareness Link D, CROSS-APP.md rule 7).

`GET /cross-app/summary?start=&end=` — the household's money shape (income/spend/net + grocery
spend + savings-goal target) for a window. RS256-only (`get_cross_app_user` — Magpie post-dates
the HS256 retirement plan), read-only, whole-dollar aggregates never rows (§6). Magpie is
tailnet-only, so a consumer reaches this only on the tailnet / same host.
"""

import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.database import get_db
from app.security import CrossAppUser
from app.services.cross_app_provider import build_summary

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/cross-app", tags=["cross-app"])

DbSession = Annotated[AsyncSession, Depends(get_db)]

MAX_RANGE_DAYS = 92  # a quarter — a grocery tile reads a month; a digest a week/month


@router.get("/summary")
async def summary(
    current_user: CrossAppUser,
    db: DbSession,
    start: datetime.date = Query(..., description="Range start (inclusive)"),
    end: datetime.date = Query(..., description="Range end (inclusive)"),
):
    if end < start:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "end must be on or after start")
    if (end - start).days + 1 > MAX_RANGE_DAYS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"range is capped at {MAX_RANGE_DAYS} days"
        )
    return await build_summary(db, current_user.id, start, end)
