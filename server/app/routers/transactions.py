import datetime
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.transaction import (
    MonthlySummaryOut,
    TransactionCreate,
    TransactionOut,
    TransactionUpdate,
)
from app.security import CurrentUser
from app.services.transaction_service import (
    create_transaction,
    delete_transaction,
    get_transaction,
    list_transactions,
    monthly_summary,
    unpair_transaction,
    update_transaction,
)

router = APIRouter(prefix="/transactions", tags=["transactions"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.get("", response_model=list[TransactionOut])
async def all_transactions(
    current_user: CurrentUser,
    db: DbSession,
    start: datetime.date | None = Query(default=None),
    end: datetime.date | None = Query(default=None),
    review_state: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=500),  # F14: opt-in pagination (cap 500)
    offset: int = Query(default=0, ge=0),
):
    return await list_transactions(
        db,
        current_user.id,
        start=start,
        end=end,
        review_state=review_state,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=TransactionOut, status_code=status.HTTP_201_CREATED)
async def create_new_transaction(req: TransactionCreate, current_user: CurrentUser, db: DbSession):
    return await create_transaction(db, current_user.id, req)


@router.get("/summary", response_model=MonthlySummaryOut)
async def summary(
    current_user: CurrentUser,
    db: DbSession,
    year: Annotated[int, Query(ge=2000, le=2100)],
    month: Annotated[int, Query(ge=1, le=12)],
):
    """Home's month cash-flow panel. Declared before /{transaction_id} so "summary" never
    parses as a transaction id."""
    result = await monthly_summary(db, current_user.id, year, month)
    return MonthlySummaryOut(
        year=year,
        month=month,
        income_cents=result.income_cents,
        spend_cents=result.spend_cents,
        net_cents=result.net_cents,
    )


@router.get("/{transaction_id}", response_model=TransactionOut)
async def one_transaction(transaction_id: uuid.UUID, current_user: CurrentUser, db: DbSession):
    return await get_transaction(db, current_user.id, transaction_id)


@router.patch("/{transaction_id}", response_model=TransactionOut)
async def patch_transaction(
    transaction_id: uuid.UUID, req: TransactionUpdate, current_user: CurrentUser, db: DbSession
):
    return await update_transaction(db, current_user.id, transaction_id, req)


@router.post("/{transaction_id}/unpair", response_model=list[TransactionOut])
async def unpair(transaction_id: uuid.UUID, current_user: CurrentUser, db: DbSession):
    """Dissolve the transfer pair this transaction belongs to (F12) — both legs revert to their
    sign-based kind and return to the review queue."""
    return await unpair_transaction(db, current_user.id, transaction_id)


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_transaction(transaction_id: uuid.UUID, current_user: CurrentUser, db: DbSession):
    await delete_transaction(db, current_user.id, transaction_id)
