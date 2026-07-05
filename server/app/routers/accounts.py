import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.account import AccountCreate, AccountOut, AccountUpdate
from app.security import CurrentUser
from app.services.account_service import (
    create_account,
    delete_account,
    get_account,
    list_accounts,
    update_account,
)

router = APIRouter(prefix="/accounts", tags=["accounts"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.get("", response_model=list[AccountOut])
async def all_accounts(current_user: CurrentUser, db: DbSession):
    return await list_accounts(db, current_user.id)


@router.post("", response_model=AccountOut, status_code=status.HTTP_201_CREATED)
async def create_new_account(req: AccountCreate, current_user: CurrentUser, db: DbSession):
    return await create_account(db, current_user.id, req)


@router.get("/{account_id}", response_model=AccountOut)
async def one_account(account_id: uuid.UUID, current_user: CurrentUser, db: DbSession):
    return await get_account(db, current_user.id, account_id)


@router.patch("/{account_id}", response_model=AccountOut)
async def patch_account(
    account_id: uuid.UUID, req: AccountUpdate, current_user: CurrentUser, db: DbSession
):
    return await update_account(db, current_user.id, account_id, req)


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_account(account_id: uuid.UUID, current_user: CurrentUser, db: DbSession):
    await delete_account(db, current_user.id, account_id)
