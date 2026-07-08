import uuid

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.schemas.category import CategoryCreate, CategoryUpdate


async def list_categories(db: AsyncSession, user_id: uuid.UUID) -> list[Category]:
    """Every shared/seeded category (user_id NULL) plus this user's own, name-sorted."""
    result = await db.execute(
        select(Category)
        .where(or_(Category.user_id.is_(None), Category.user_id == user_id))
        .order_by(Category.name)
    )
    return list(result.scalars().all())


async def create_category(db: AsyncSession, user_id: uuid.UUID, req: CategoryCreate) -> Category:
    category = Category(user_id=user_id, name=req.name)
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return category


async def update_category(
    db: AsyncSession, user_id: uuid.UUID, category_id: uuid.UUID, req: CategoryUpdate
) -> Category:
    """Rename one of the user's own categories. Shared/seeded categories (user_id NULL) are
    read-only, so the ownership filter is the guard — renaming a shared one 404s, same as
    delete."""
    result = await db.execute(
        select(Category).where(Category.id == category_id, Category.user_id == user_id)
    )
    category = result.scalar_one_or_none()
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    category.name = req.name
    await db.commit()
    await db.refresh(category)
    return category


async def delete_category(db: AsyncSession, user_id: uuid.UUID, category_id: uuid.UUID) -> None:
    """Only the user's own categories can be deleted — shared/seeded ones (user_id NULL) are
    read-only, so the ownership filter here doubles as that guard."""
    result = await db.execute(
        select(Category).where(Category.id == category_id, Category.user_id == user_id)
    )
    category = result.scalar_one_or_none()
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    await db.delete(category)
    await db.commit()
