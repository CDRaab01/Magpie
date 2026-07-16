import datetime
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.summary import (
    CategorySummaryItem,
    CategorySummaryOut,
    HistoryOut,
    MerchantSummaryItem,
    MerchantSummaryOut,
    MonthSummaryOut,
    SafeToSpendOut,
)
from app.security import LedgerUser
from app.services.summary_service import (
    category_summary,
    safe_to_spend,
    spending_history,
    top_merchants,
)

router = APIRouter(prefix="/summary", tags=["summary"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


@router.get("/history", response_model=HistoryOut)
async def history(
    current_user: LedgerUser,
    db: DbSession,
    months: Annotated[int, Query(ge=1, le=36)] = 6,
):
    """The last N months of income/spend/net (oldest first) — the trend chart's series."""
    series = await spending_history(db, current_user.id, months=months, now=_utc_now())
    return HistoryOut(
        months=[
            MonthSummaryOut(
                year=m.year,
                month=m.month,
                income_cents=m.income_cents,
                spend_cents=m.spend_cents,
                net_cents=m.net_cents,
            )
            for m in series
        ]
    )


@router.get("/categories", response_model=CategorySummaryOut)
async def categories_breakdown(
    current_user: LedgerUser,
    db: DbSession,
    month: Annotated[datetime.date, Query()],
):
    """Net spend per category for the month, largest spend first (the category breakdown)."""
    items = await category_summary(db, current_user.id, month)
    return CategorySummaryOut(
        month=month,
        categories=[
            CategorySummaryItem(
                category_id=str(cid) if cid is not None else None,
                category_name=name,
                spend_cents=cents,
            )
            for cid, name, cents in items
        ],
    )


@router.get("/merchants", response_model=MerchantSummaryOut)
async def merchants_breakdown(
    current_user: LedgerUser,
    db: DbSession,
    month: Annotated[datetime.date, Query()],
    category_id: uuid.UUID | None = Query(default=None),
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
):
    """The top merchants by spend for the month — optionally within one category (drill-down)."""
    rows = await top_merchants(db, current_user.id, month, category_id=category_id, limit=limit)
    return MerchantSummaryOut(
        month=month,
        merchants=[
            MerchantSummaryItem(merchant=m, spend_cents=cents, transaction_count=count)
            for m, cents, count in rows
        ],
    )


@router.get("/safe-to-spend", response_model=SafeToSpendOut)
async def safe_to_spend_endpoint(current_user: LedgerUser, db: DbSession):
    """The headline number: depository balances minus bills due before the next paycheck."""
    result = await safe_to_spend(db, current_user.id, now=_utc_now())
    return SafeToSpendOut(**result)
