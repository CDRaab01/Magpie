"""Household (family mode) membership management.

These endpoints operate on the *real* caller (``CurrentUser``), not the resolved ledger owner —
managing who shares the ledger is an identity concern. The financial routers use ``LedgerUser``
instead, which is where the actual sharing happens.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.household import (
    AddMemberRequest,
    HouseholdMemberOut,
    HouseholdOut,
    InviteOut,
)
from app.security import CurrentUser
from app.services.household_service import (
    accept_invite,
    add_member_by_email,
    decline_invite,
    leave_household,
    list_household,
    pending_invite,
    remove_member,
)

router = APIRouter(prefix="/household", tags=["household"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


async def _current_household(current_user, db: AsyncSession) -> HouseholdOut:
    household, members = await list_household(db, current_user.id)
    if household is None:
        # Solo: present the caller as a one-person, not-yet-shared household.
        return HouseholdOut(
            members=[
                HouseholdMemberOut(
                    user_id=current_user.id,
                    name=current_user.name,
                    email=current_user.email,
                    is_owner=True,
                )
            ],
            you_are_owner=True,
            shared=False,
        )
    return HouseholdOut(
        members=[
            HouseholdMemberOut(
                user_id=m.id,
                name=m.name,
                email=m.email,
                is_owner=(m.id == household.owner_user_id),
                status=st,
            )
            for m, st in members
        ],
        you_are_owner=(household.owner_user_id == current_user.id),
        shared=sum(1 for _, st in members if st == "active") > 1,
    )


@router.get("", response_model=HouseholdOut)
async def get_my_household(current_user: CurrentUser, db: DbSession):
    return await _current_household(current_user, db)


@router.post("/members", response_model=HouseholdOut, status_code=status.HTTP_201_CREATED)
async def add_member(req: AddMemberRequest, current_user: CurrentUser, db: DbSession):
    """Owner **invites** another Magpie user by email (they must have signed in once). The invite is
    PENDING — nothing shares until they accept it, so no one is silently added to your finances."""
    await add_member_by_email(db, current_user.id, req.email)
    return await _current_household(current_user, db)


@router.get("/invite", response_model=InviteOut | None)
async def my_invite(current_user: CurrentUser, db: DbSession):
    """The household invite awaiting the caller's response, or null."""
    invite = await pending_invite(db, current_user.id)
    if invite is None:
        return None
    household, owner = invite
    return InviteOut(household_id=household.id, owner_name=owner.name, owner_email=owner.email)


@router.post("/accept", response_model=HouseholdOut)
async def accept(current_user: CurrentUser, db: DbSession):
    """Accept your pending invite — from now on you share the household's ledger."""
    await accept_invite(db, current_user.id)
    return await _current_household(current_user, db)


@router.post("/decline", status_code=status.HTTP_204_NO_CONTENT)
async def decline(current_user: CurrentUser, db: DbSession):
    await decline_invite(db, current_user.id)


@router.delete("/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove(user_id: uuid.UUID, current_user: CurrentUser, db: DbSession):
    await remove_member(db, current_user.id, user_id)


@router.post("/leave", status_code=status.HTTP_204_NO_CONTENT)
async def leave(current_user: CurrentUser, db: DbSession):
    """Leave the household; if you're the owner this disbands it (everyone reverts to solo)."""
    await leave_household(db, current_user.id)
