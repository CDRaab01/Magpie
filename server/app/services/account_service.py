import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
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
