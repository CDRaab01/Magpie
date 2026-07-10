import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ledger.balances import (
    CheckpointAnchor,
    DatedAmount,
    derived_balance,
    reconciliation_delta,
)
from app.models.account import Account
from app.models.statement_checkpoint import StatementCheckpoint
from app.models.transaction import COUNTABLE_STATUSES, Transaction
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


async def _checkpoint_anchors(
    db: AsyncSession, account_id: uuid.UUID
) -> tuple[CheckpointAnchor | None, CheckpointAnchor | None]:
    """The account's earliest and latest statement checkpoints as balance anchors, or
    (None, None) if it has never been reconciled. F1: the earliest is what the derived balance
    is anchored to; the pair bounds the reconciliation window (app/ledger/balances.py)."""
    result = await db.execute(
        select(StatementCheckpoint)
        .where(StatementCheckpoint.account_id == account_id)
        .order_by(StatementCheckpoint.statement_date, StatementCheckpoint.id)
    )
    checkpoints = list(result.scalars().all())
    if not checkpoints:
        return None, None
    to_anchor = lambda cp: CheckpointAnchor(cp.statement_date, cp.stated_balance)  # noqa: E731
    return to_anchor(checkpoints[0]), to_anchor(checkpoints[-1])


async def _dated_amounts(db: AsyncSession, account_id: uuid.UUID) -> list[DatedAmount]:
    result = await db.execute(
        select(Transaction.date, Transaction.amount).where(
            Transaction.account_id == account_id,
            # A split parent carries the full amount; its child parts are excluded so the money
            # isn't double-counted in the balance (#26).
            Transaction.split_parent_id.is_(None),
            # An expired auth hold never became money; it must not move the balance.
            Transaction.status.in_(COUNTABLE_STATUSES),
        )
    )
    return [DatedAmount(date=d, amount=a) for d, a in result.all()]


async def compute_account_balance(db: AsyncSession, account_id: uuid.UUID) -> int:
    """The account's derived balance (CLAUDE.md §9), anchored at the earliest checkpoint (F1)
    — sums every transaction after the anchor, transfers included (unlike the household rollup;
    see app/ledger/balances.py)."""
    earliest, _ = await _checkpoint_anchors(db, account_id)
    return derived_balance(await _dated_amounts(db, account_id), anchor=earliest)


async def compute_balance_delta(db: AsyncSession, account_id: uuid.UUID) -> int | None:
    """Ledger-vs-statement delta (the honesty meter, F1): does the ledger fully account for the
    money that moved between the earliest and latest checkpoints? None if this account has never
    been reconciled against a statement; zero when a single checkpoint anchors it."""
    earliest, latest = await _checkpoint_anchors(db, account_id)
    if earliest is None:
        return None
    return reconciliation_delta(await _dated_amounts(db, account_id), earliest, latest)
