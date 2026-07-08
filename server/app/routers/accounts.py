import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.account import Account
from app.schemas.account import AccountCreate, AccountOut, AccountUpdate
from app.security import CurrentUser
from app.services.account_service import (
    compute_account_balance,
    compute_balance_delta,
    create_account,
    delete_account,
    get_account,
    list_accounts,
    update_account,
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
