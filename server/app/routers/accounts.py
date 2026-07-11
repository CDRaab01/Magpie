import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.account import Account
from app.models.statement_checkpoint import StatementCheckpoint
from app.schemas.account import (
    AccountCreate,
    AccountOut,
    AccountUpdate,
    CheckpointCreate,
    CheckpointOut,
)
from app.security import CurrentUser
from app.services.account_service import (
    compute_account_balance,
    compute_balance_delta,
    create_account,
    delete_account,
    get_account,
    list_accounts,
    list_checkpoints,
    update_account,
    upsert_checkpoint,
)

router = APIRouter(prefix="/accounts", tags=["accounts"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


async def _to_out(db: AsyncSession, account: Account) -> AccountOut:
    balance = await compute_account_balance(db, account.id)
    delta = await compute_balance_delta(db, account.id)
    return AccountOut(
        id=account.id,
        name=account.name,
        institution=account.institution,
        type=account.type,
        last4=account.last4,
        active=account.active,
        balance_cents=balance,
        balance_delta_cents=delta,
    )


@router.get("", response_model=list[AccountOut])
async def all_accounts(current_user: CurrentUser, db: DbSession):
    accounts = await list_accounts(db, current_user.id)
    return [await _to_out(db, a) for a in accounts]


@router.post("", response_model=AccountOut, status_code=status.HTTP_201_CREATED)
async def create_new_account(req: AccountCreate, current_user: CurrentUser, db: DbSession):
    account = await create_account(db, current_user.id, req)
    return await _to_out(db, account)


@router.get("/{account_id}", response_model=AccountOut)
async def one_account(account_id: uuid.UUID, current_user: CurrentUser, db: DbSession):
    account = await get_account(db, current_user.id, account_id)
    return await _to_out(db, account)


@router.patch("/{account_id}", response_model=AccountOut)
async def patch_account(
    account_id: uuid.UUID, req: AccountUpdate, current_user: CurrentUser, db: DbSession
):
    account = await update_account(db, current_user.id, account_id, req)
    return await _to_out(db, account)


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_account(account_id: uuid.UUID, current_user: CurrentUser, db: DbSession):
    await delete_account(db, current_user.id, account_id)


def _checkpoint_out(cp: StatementCheckpoint) -> CheckpointOut:
    return CheckpointOut(
        id=cp.id,
        account_id=cp.account_id,
        statement_date=cp.statement_date,
        stated_balance_cents=cp.stated_balance,
        import_batch_id=cp.import_batch_id,
    )


@router.get("/{account_id}/checkpoints", response_model=list[CheckpointOut])
async def account_checkpoints(account_id: uuid.UUID, current_user: CurrentUser, db: DbSession):
    checkpoints = await list_checkpoints(db, current_user.id, account_id)
    return [_checkpoint_out(cp) for cp in checkpoints]


@router.post(
    "/{account_id}/checkpoints",
    response_model=CheckpointOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_checkpoint(
    account_id: uuid.UUID, req: CheckpointCreate, current_user: CurrentUser, db: DbSession
):
    """Manually anchor a statement balance (ROADMAP #4). Re-posting the same statement_date corrects
    the balance in place rather than creating a duplicate anchor. Once a second checkpoint exists,
    the account's reconciliation delta becomes a real honesty signal and the v1 parity clock ticks."""
    cp = await upsert_checkpoint(
        db, current_user.id, account_id, req.statement_date, req.stated_balance_cents
    )
    return _checkpoint_out(cp)
