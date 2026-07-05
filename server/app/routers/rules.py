import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.rule import RuleCreate, RuleOut, RuleUpdate
from app.security import CurrentUser
from app.services.rule_service import create_rule, delete_rule, get_rule, list_rules, update_rule

router = APIRouter(prefix="/rules", tags=["rules"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.get("", response_model=list[RuleOut])
async def all_rules(current_user: CurrentUser, db: DbSession):
    return await list_rules(db, current_user.id)


@router.post("", response_model=RuleOut, status_code=status.HTTP_201_CREATED)
async def create_new_rule(req: RuleCreate, current_user: CurrentUser, db: DbSession):
    return await create_rule(db, current_user.id, req)


@router.get("/{rule_id}", response_model=RuleOut)
async def one_rule(rule_id: uuid.UUID, current_user: CurrentUser, db: DbSession):
    return await get_rule(db, current_user.id, rule_id)


@router.patch("/{rule_id}", response_model=RuleOut)
async def patch_rule(rule_id: uuid.UUID, req: RuleUpdate, current_user: CurrentUser, db: DbSession):
    return await update_rule(db, current_user.id, rule_id, req)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_rule(rule_id: uuid.UUID, current_user: CurrentUser, db: DbSession):
    await delete_rule(db, current_user.id, rule_id)
