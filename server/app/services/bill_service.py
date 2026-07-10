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
from app.rules.bill_matching import (
    BILL_PAYMENT_KINDS,
    DEFAULT_WINDOW_DAYS,
    BillCandidate,
    PaymentCandidate,
    find_bill_payment,
)
from app.schemas.bill import BillStatementCreate


async def _owned_account(db: AsyncSession, user_id: uuid.UUID, account_id: uuid.UUID) -> Account:
    result = await db.execute(
        select(Account).where(Account.id == account_id, Account.user_id == user_id)
    )
    account = result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")
    return account


async def _find_payment(db: AsyncSession, bill: BillStatement) -> PaymentCandidate | None:
    """The transaction that settles this bill, or None (F13).

    The pool is narrowed in SQL — same account, inside the due-date window, an outflow of a
    payment-shaped kind, not already claimed by another bill — so a backfilled account with
    thousands of rows never lands in Python (F14 discipline). `find_bill_payment` then applies
    the exact-amount rule and picks the closest date.
    """
    lo = bill.due_date - datetime.timedelta(days=DEFAULT_WINDOW_DAYS)
    hi = bill.due_date + datetime.timedelta(days=DEFAULT_WINDOW_DAYS)

    # `NOT IN (…)` yields no rows at all if the subquery emits a single NULL, so the
    # is_not(None) filter is load-bearing, not decoration.
    claimed = select(BillStatement.matched_transaction_id).where(
        BillStatement.matched_transaction_id.is_not(None)
    )
    rows = await db.execute(
        select(
            Transaction.id,
            Transaction.account_id,
            Transaction.amount,
            Transaction.date,
            Transaction.kind,
        ).where(
            Transaction.account_id == bill.account_id,
            Transaction.date >= lo,
            Transaction.date <= hi,
            Transaction.amount < 0,
            Transaction.kind.in_(BILL_PAYMENT_KINDS),
            # A split child duplicates part of its parent's amount; the parent is the payment.
            Transaction.split_parent_id.is_(None),
            Transaction.id.not_in(claimed),
        )
    )
    pool = [PaymentCandidate(str(r.id), str(r.account_id), r.amount, r.date, r.kind) for r in rows]
    return find_bill_payment(
        BillCandidate(str(bill.id), str(bill.account_id), bill.amount_due, bill.due_date), pool
    )


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
    match = await _find_payment(db, bill)
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
    match = await _find_payment(db, bill)
    if match is not None:
        bill.matched_transaction_id = uuid.UUID(match.id)
        await db.commit()
        await db.refresh(bill)
    return bill
