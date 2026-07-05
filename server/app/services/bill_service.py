"""Bills domain (CLAUDE.md §4/§10): CRUD, matching a bill to its later payment, and the
cash-flow calendar read ("due before next paycheck"). Scoped via a join to `accounts.user_id`
— `BillStatement` carries no `user_id` of its own, same as `StatementCheckpoint` (Phase 3):
`account_id` is required, so there's no nullable-join gap to worry about.
"""

import datetime
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.bill_statement import BillStatement
from app.models.transaction import Transaction
from app.rules.bill_matching import BillCandidate, PaymentCandidate, find_bill_payment
from app.schemas.bill import BillStatementCreate


async def _owned_account(db: AsyncSession, user_id: uuid.UUID, account_id: uuid.UUID) -> Account:
    result = await db.execute(
        select(Account).where(Account.id == account_id, Account.user_id == user_id)
    )
    account = result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")
    return account


async def create_bill(
    db: AsyncSession, user_id: uuid.UUID, req: BillStatementCreate, *, now: datetime.datetime
) -> BillStatement:
    await _owned_account(db, user_id, req.account_id)
    bill = BillStatement(
        biller=req.biller,
        account_id=req.account_id,
        amount_due=req.amount_due,
        due_date=req.due_date,
        issued_at=req.issued_at or now,
    )
    db.add(bill)
    await db.flush()

    # Try to match immediately — a bill created after its payment already posted (e.g. a
    # backfilled historical bill) shouldn't sit "missing" forever.
    payments_result = await db.execute(
        select(Transaction).where(Transaction.account_id == req.account_id)
    )
    pool = [
        PaymentCandidate(str(t.id), str(t.account_id), t.amount, t.date)
        for t in payments_result.scalars().all()
    ]
    match = find_bill_payment(
        BillCandidate(str(bill.id), str(req.account_id), req.amount_due, req.due_date), pool
    )
    if match is not None:
        bill.matched_transaction_id = uuid.UUID(match.id)

    await db.commit()
    await db.refresh(bill)
    return bill


async def list_bills(db: AsyncSession, user_id: uuid.UUID) -> list[BillStatement]:
    result = await db.execute(
        select(BillStatement)
        .join(Account, BillStatement.account_id == Account.id)
        .where(Account.user_id == user_id)
        .order_by(BillStatement.due_date)
    )
    return list(result.scalars().all())


async def get_bill(db: AsyncSession, user_id: uuid.UUID, bill_id: uuid.UUID) -> BillStatement:
    result = await db.execute(
        select(BillStatement)
        .join(Account, BillStatement.account_id == Account.id)
        .where(BillStatement.id == bill_id, Account.user_id == user_id)
    )
    bill = result.scalar_one_or_none()
    if bill is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bill not found")
    return bill


async def rematch_bill(db: AsyncSession, user_id: uuid.UUID, bill_id: uuid.UUID) -> BillStatement:
    """Re-checks an unmatched bill against current transactions — useful right after a CSV
    import or email poll brings in the payment that settles it."""
    bill = await get_bill(db, user_id, bill_id)
    if bill.matched_transaction_id is not None:
        return bill
    payments_result = await db.execute(
        select(Transaction).where(Transaction.account_id == bill.account_id)
    )
    pool = [
        PaymentCandidate(str(t.id), str(t.account_id), t.amount, t.date)
        for t in payments_result.scalars().all()
    ]
    match = find_bill_payment(
        BillCandidate(str(bill.id), str(bill.account_id), bill.amount_due, bill.due_date), pool
    )
    if match is not None:
        bill.matched_transaction_id = uuid.UUID(match.id)
        await db.commit()
        await db.refresh(bill)
    return bill
