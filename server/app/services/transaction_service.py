import datetime
import uuid
from calendar import monthrange

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ledger.classify import validate_kind_amount_sign
from app.ledger.rollups import MonthlyRollup, TransactionForRollup, rollup_month
from app.models.account import Account
from app.models.transaction import Transaction
from app.schemas.transaction import TransactionCreate, TransactionUpdate


async def _owned_account(db: AsyncSession, user_id: uuid.UUID, account_id: uuid.UUID) -> Account:
    result = await db.execute(
        select(Account).where(Account.id == account_id, Account.user_id == user_id)
    )
    account = result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")
    return account


async def create_transaction(
    db: AsyncSession, user_id: uuid.UUID, req: TransactionCreate
) -> Transaction:
    await _owned_account(db, user_id, req.account_id)  # 404s if not this user's account

    try:
        validate_kind_amount_sign(req.kind, req.amount)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e))

    # Manual entries are trusted immediately — there is no draft state to review (unlike
    # email/CSV-ingested transactions, Phase 3/4, which start "needs_review").
    txn = Transaction(
        account_id=req.account_id,
        amount=req.amount,
        currency=req.currency,
        date=req.date,
        status=req.status,
        merchant_raw=req.merchant_raw,
        category_id=req.category_id,
        kind=req.kind,
        review_state="confirmed",
        source="manual",
    )
    db.add(txn)
    await db.commit()
    await db.refresh(txn)
    return txn


async def list_transactions(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    start: datetime.date | None = None,
    end: datetime.date | None = None,
    review_state: str | None = None,
) -> list[Transaction]:
    query = (
        select(Transaction)
        .join(Account, Transaction.account_id == Account.id)
        .where(Account.user_id == user_id)
        .order_by(Transaction.date.desc(), Transaction.created_at.desc())
    )
    if start is not None:
        query = query.where(Transaction.date >= start)
    if end is not None:
        query = query.where(Transaction.date <= end)
    if review_state is not None:
        query = query.where(Transaction.review_state == review_state)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_transaction(
    db: AsyncSession, user_id: uuid.UUID, transaction_id: uuid.UUID
) -> Transaction:
    result = await db.execute(
        select(Transaction)
        .join(Account, Transaction.account_id == Account.id)
        .where(Transaction.id == transaction_id, Account.user_id == user_id)
    )
    txn = result.scalar_one_or_none()
    if txn is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transaction not found")
    return txn


async def update_transaction(
    db: AsyncSession, user_id: uuid.UUID, transaction_id: uuid.UUID, req: TransactionUpdate
) -> Transaction:
    """The review queue's confirm/correct action lives here too: a human accepting or fixing a
    rule/AI draft (Phase 5) sets review_state (and optionally kind) alongside category —
    `kind` only re-validates the sign invariant when both are supplied together, since a
    lone `kind` change without knowing the current amount's sign would be unsafe to check."""
    txn = await get_transaction(db, user_id, transaction_id)
    if req.category_id is not None:
        txn.category_id = req.category_id
    if req.merchant_raw is not None:
        txn.merchant_raw = req.merchant_raw
    if req.kind is not None:
        try:
            validate_kind_amount_sign(req.kind, txn.amount)
        except ValueError as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e))
        txn.kind = req.kind
    if req.review_state is not None:
        txn.review_state = req.review_state
    await db.commit()
    await db.refresh(txn)
    return txn


async def delete_transaction(
    db: AsyncSession, user_id: uuid.UUID, transaction_id: uuid.UUID
) -> None:
    txn = await get_transaction(db, user_id, transaction_id)
    await db.delete(txn)
    await db.commit()


async def monthly_summary(
    db: AsyncSession, user_id: uuid.UUID, year: int, month: int
) -> MonthlyRollup:
    """The Home screen's month cash-flow panel — pure math in app/ledger/, this just feeds it."""
    start = datetime.date(year, month, 1)
    end = datetime.date(year, month, monthrange(year, month)[1])
    txns = await list_transactions(db, user_id, start=start, end=end)
    return rollup_month(TransactionForRollup(t.kind, t.amount) for t in txns)
