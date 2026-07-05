import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ledger.balances import (
    BalanceCheckpoint,
    TransactionForBalance,
    account_balance,
    balance_delta,
)
from app.models.account import Account
from app.models.statement_checkpoint import StatementCheckpoint
from app.models.transaction import Transaction
from app.schemas.account import AccountCreate, AccountUpdate


async def list_accounts(db: AsyncSession, user_id: uuid.UUID) -> list[Account]:
    result = await db.execute(
        select(Account).where(Account.user_id == user_id).order_by(Account.name)
    )
    return list(result.scalars().all())


async def create_account(db: AsyncSession, user_id: uuid.UUID, req: AccountCreate) -> Account:
    account = Account(
        user_id=user_id,
        name=req.name,
        institution=req.institution,
        type=req.type,
        last4=req.last4,
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return account


async def get_account(db: AsyncSession, user_id: uuid.UUID, account_id: uuid.UUID) -> Account:
    result = await db.execute(
        select(Account).where(Account.id == account_id, Account.user_id == user_id)
    )
    account = result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")
    return account


async def update_account(
    db: AsyncSession, user_id: uuid.UUID, account_id: uuid.UUID, req: AccountUpdate
) -> Account:
    account = await get_account(db, user_id, account_id)
    if req.name is not None:
        account.name = req.name
    if req.active is not None:
        account.active = req.active
    await db.commit()
    await db.refresh(account)
    return account


async def delete_account(db: AsyncSession, user_id: uuid.UUID, account_id: uuid.UUID) -> None:
    account = await get_account(db, user_id, account_id)
    await db.delete(account)
    await db.commit()


async def compute_account_balance(db: AsyncSession, account_id: uuid.UUID) -> int:
    """The account's derived balance (CLAUDE.md §9) — sums every transaction, transfers
    included (unlike the household rollup; see app/ledger/balances.py)."""
    result = await db.execute(
        select(Transaction.amount).where(Transaction.account_id == account_id)
    )
    return account_balance(TransactionForBalance(a) for a in result.scalars().all())


async def compute_balance_delta(
    db: AsyncSession, account_id: uuid.UUID, computed_cents: int
) -> int | None:
    """Ledger-vs-statement delta against the most recent import checkpoint, or None if this
    account has never been reconciled against a statement."""
    result = await db.execute(
        select(StatementCheckpoint)
        .where(StatementCheckpoint.account_id == account_id)
        .order_by(StatementCheckpoint.statement_date.desc())
        .limit(1)
    )
    checkpoint = result.scalar_one_or_none()
    stated_cents = checkpoint.stated_balance if checkpoint else None
    return balance_delta(
        BalanceCheckpoint(computed_cents=computed_cents, stated_cents=stated_cents)
    )
