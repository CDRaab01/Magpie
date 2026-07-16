import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.category import CategoryCreate, CategoryOut, CategoryUpdate
from app.security import LedgerUser
from app.services.category_service import (
    create_category,
    delete_category,
    list_categories,
    update_category,
)

router = APIRouter(prefix="/categories", tags=["categories"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.get("", response_model=list[CategoryOut])
async def all_categories(current_user: LedgerUser, db: DbSession):
    categories = await list_categories(db, current_user.id)
    return [CategoryOut(id=c.id, name=c.name, shared=c.user_id is None) for c in categories]


@router.post("", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
async def create_new_category(req: CategoryCreate, current_user: LedgerUser, db: DbSession):
    c = await create_category(db, current_user.id, req)
    return CategoryOut(id=c.id, name=c.name, shared=False)


@router.patch("/{category_id}", response_model=CategoryOut)
async def rename_category(
    category_id: uuid.UUID, req: CategoryUpdate, current_user: LedgerUser, db: DbSession
):
    """Rename one of the user's own categories (shared/seeded ones are read-only → 404)."""
    c = await update_category(db, current_user.id, category_id, req)
    return CategoryOut(id=c.id, name=c.name, shared=False)


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_category(category_id: uuid.UUID, current_user: LedgerUser, db: DbSession):
    await delete_category(db, current_user.id, category_id)
