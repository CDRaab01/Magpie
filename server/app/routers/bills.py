import datetime
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.bill_statement import BillStatement
from app.rules.bill_matching import is_bill_missing
from app.schemas.bill import BillStatementCreate, BillStatementOut
from app.security import CurrentUser
from app.services.bill_service import create_bill, get_bill, list_bills, rematch_bill

router = APIRouter(prefix="/bills", tags=["bills"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


def _to_out(bill: BillStatement, *, today: datetime.date) -> BillStatementOut:
    missing = bill.matched_transaction_id is None and is_bill_missing(bill.due_date, today)
    return BillStatementOut(
        id=bill.id,
        biller=bill.biller,
        account_id=bill.account_id,
        amount_due=bill.amount_due,
        due_date=bill.due_date,
        issued_at=bill.issued_at,
        matched_transaction_id=bill.matched_transaction_id,
        is_missing=missing,
    )


@router.get("", response_model=list[BillStatementOut])
async def all_bills(current_user: CurrentUser, db: DbSession):
    today = datetime.datetime.now(datetime.timezone.utc).date()
    return [_to_out(b, today=today) for b in await list_bills(db, current_user.id)]


@router.post("", response_model=BillStatementOut, status_code=status.HTTP_201_CREATED)
async def create_new_bill(req: BillStatementCreate, current_user: CurrentUser, db: DbSession):
    now = datetime.datetime.now(datetime.timezone.utc)
    bill = await create_bill(db, current_user.id, req, now=now)
    return _to_out(bill, today=now.date())


@router.get("/{bill_id}", response_model=BillStatementOut)
async def one_bill(bill_id: uuid.UUID, current_user: CurrentUser, db: DbSession):
    today = datetime.datetime.now(datetime.timezone.utc).date()
    return _to_out(await get_bill(db, current_user.id, bill_id), today=today)


@router.post("/{bill_id}/rematch", response_model=BillStatementOut)
async def rematch_one_bill(bill_id: uuid.UUID, current_user: CurrentUser, db: DbSession):
    today = datetime.datetime.now(datetime.timezone.utc).date()
    return _to_out(await rematch_bill(db, current_user.id, bill_id), today=today)
