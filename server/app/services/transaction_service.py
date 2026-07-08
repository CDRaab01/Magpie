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


def _sign_based_kind(amount: int) -> str:
    """The neutral kind a former transfer leg reverts to when a pair is dissolved — sign is the
    only signal left once "transfer" is taken away (income if it came in, spend if it went out).
    The human re-categorizes it in the review queue."""
    return "income" if amount > 0 else "spend"


async def _dissolve_transfer_group(
    db: AsyncSession, user_id: uuid.UUID, group: str
) -> list[Transaction]:
    """Break a transfer_group cleanly (F12): clear the group on every leg, revert each to its
    sign-based kind, and route it back to review. Leaving one leg a "transfer" while its partner
    is corrected is exactly the dangling half-group that violates the zero-sum invariant."""
    result = await db.execute(
        select(Transaction)
        .join(Account, Transaction.account_id == Account.id)
        .where(Account.user_id == user_id, Transaction.transfer_group == group)
    )
    legs = list(result.scalars().all())
    for leg in legs:
        leg.transfer_group = None
        leg.kind = _sign_based_kind(leg.amount)
        leg.review_state = "needs_review"
    return legs


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
        # F12: changing a transfer leg's kind away from "transfer" must dissolve the whole
        # group, not just this row — otherwise the partner is left a dangling half-group.
        if txn.transfer_group is not None and req.kind != "transfer":
            await _dissolve_transfer_group(db, user_id, txn.transfer_group)
        txn.kind = req.kind
    if req.review_state is not None:
        txn.review_state = req.review_state
    await db.commit()
    await db.refresh(txn)
    return txn


async def unpair_transaction(
    db: AsyncSession, user_id: uuid.UUID, transaction_id: uuid.UUID
) -> list[Transaction]:
    """The review-queue's un-pair affordance (F12): dissolve the transfer group this
    transaction belongs to, returning every affected leg so the client can refresh them."""
    txn = await get_transaction(db, user_id, transaction_id)
    if txn.transfer_group is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Transaction is not part of a transfer pair"
        )
    legs = await _dissolve_transfer_group(db, user_id, txn.transfer_group)
    await db.commit()
    for leg in legs:
        await db.refresh(leg)
    return legs


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
