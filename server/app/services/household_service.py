"""Household (family-mode) membership + the ledger-owner resolution.

The one function the whole feature turns on is :func:`resolve_ledger_owner_id`: every financial
request from a member is scoped to the household **owner's** user id, so both people read and write
one shared ledger. Membership management (invite / list / remove / leave) is owner-gated where it
should be; a user belongs to at most one household.
"""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.household import Household, HouseholdMember
from app.models.user import User


async def resolve_ledger_owner_id(db: AsyncSession, user_id: uuid.UUID) -> uuid.UUID:
    """The user id whose financial data this user operates on. For a household member that is the
    household **owner**; for everyone else it is the user themselves (no household ⇒ solo)."""
    owner_id = (
        await db.execute(
            select(Household.owner_user_id)
            .join(HouseholdMember, HouseholdMember.household_id == Household.id)
            .where(HouseholdMember.user_id == user_id, HouseholdMember.status == "active")
        )
    ).scalar_one_or_none()
    return owner_id or user_id


async def _household_of(db: AsyncSession, user_id: uuid.UUID) -> Household | None:
    """The household this user *actively* shares (a pending invite grants nothing until accepted)."""
    return (
        await db.execute(
            select(Household)
            .join(HouseholdMember, HouseholdMember.household_id == Household.id)
            .where(HouseholdMember.user_id == user_id, HouseholdMember.status == "active")
        )
    ).scalar_one_or_none()


async def _any_membership(db: AsyncSession, user_id: uuid.UUID) -> HouseholdMember | None:
    """The user's membership row regardless of status (a user has at most one)."""
    return (
        await db.execute(select(HouseholdMember).where(HouseholdMember.user_id == user_id))
    ).scalar_one_or_none()


async def get_or_create_household(db: AsyncSession, user_id: uuid.UUID) -> Household:
    """The user's household, creating one they own (with themselves as the first member) if they
    aren't in one yet."""
    existing = await _household_of(db, user_id)
    if existing is not None:
        return existing
    if await _any_membership(db, user_id) is not None:
        # A pending invite is outstanding — resolve it before starting your own household.
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "You have a pending household invite — accept or decline it first",
        )
    household = Household(owner_user_id=user_id)
    db.add(household)
    await db.flush()
    db.add(HouseholdMember(household_id=household.id, user_id=user_id, status="active"))
    await db.commit()
    await db.refresh(household)
    return household


async def add_member_by_email(db: AsyncSession, requester_id: uuid.UUID, email: str) -> User:
    """Owner adds a member by their Magpie (SSO) email. The invitee must have signed into Magpie at
    least once (accounts link by email, like the sibling apps — there is no pending-invite state)."""
    household = await get_or_create_household(db, requester_id)
    if household.owner_user_id != requester_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the household owner can add members")

    target = (
        await db.execute(select(User).where(func.lower(User.email) == email.strip().lower()))
    ).scalar_one_or_none()
    if target is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No Magpie account for that email — they need to sign in to Magpie once first",
        )
    if target.id == requester_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That's your own account")

    membership = await _any_membership(db, target.id)
    if membership is not None:
        if membership.household_id == household.id:
            return target  # already invited/joined here — idempotent
        raise HTTPException(
            status.HTTP_409_CONFLICT, "That person already has a household invite or membership"
        )

    # A PENDING invite — the invitee must accept before they see anything (no silent add).
    db.add(HouseholdMember(household_id=household.id, user_id=target.id, status="pending"))
    await db.commit()
    return target


async def list_household(
    db: AsyncSession, user_id: uuid.UUID
) -> tuple[Household | None, list[tuple[User, str]]]:
    """The user's active household + its members (owner first) with each member's status
    (``active`` | ``pending``). ``(None, [])`` when solo."""
    household = await _household_of(db, user_id)
    if household is None:
        return None, []
    rows = (
        await db.execute(
            select(User, HouseholdMember.status)
            .join(HouseholdMember, HouseholdMember.user_id == User.id)
            .where(HouseholdMember.household_id == household.id)
        )
    ).all()
    rows = sorted(rows, key=lambda r: r[0].id != household.owner_user_id)  # owner first
    return household, [(u, s) for u, s in rows]


async def pending_invite(db: AsyncSession, user_id: uuid.UUID) -> tuple[Household, User] | None:
    """The household + its owner for the user's outstanding invite, or ``None``."""
    membership = await _any_membership(db, user_id)
    if membership is None or membership.status != "pending":
        return None
    household = await db.get(Household, membership.household_id)
    if household is None:
        return None
    owner = await db.get(User, household.owner_user_id)
    return household, owner


async def accept_invite(db: AsyncSession, user_id: uuid.UUID) -> None:
    membership = await _any_membership(db, user_id)
    if membership is None or membership.status != "pending":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No pending invite to accept")
    membership.status = "active"
    await db.commit()


async def decline_invite(db: AsyncSession, user_id: uuid.UUID) -> None:
    membership = await _any_membership(db, user_id)
    if membership is None or membership.status != "pending":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No pending invite to decline")
    await db.delete(membership)
    await db.commit()


async def remove_member(db: AsyncSession, requester_id: uuid.UUID, target_id: uuid.UUID) -> None:
    """Remove a member. The owner may remove anyone (but not themselves — they disband via leave);
    a member may remove only themselves."""
    household = await _household_of(db, requester_id)
    if household is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "You aren't in a household")
    if requester_id != household.owner_user_id and requester_id != target_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the owner can remove another member")
    if target_id == household.owner_user_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "The owner can't be removed — leave from the owner account to disband the household",
        )
    membership = (
        await db.execute(
            select(HouseholdMember).where(
                HouseholdMember.user_id == target_id,
                HouseholdMember.household_id == household.id,
            )
        )
    ).scalar_one_or_none()
    if membership is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not a member of your household")
    await db.delete(membership)
    await db.commit()


async def leave_household(db: AsyncSession, user_id: uuid.UUID) -> None:
    """A member leaves; the owner leaving **disbands** the household (members revert to solo — their
    own separate ledgers). The financial rows are untouched: they were always owned by real users."""
    household = await _household_of(db, user_id)
    if household is None:
        return
    if household.owner_user_id == user_id:
        await db.delete(household)  # cascade removes member rows
    else:
        membership = (
            await db.execute(
                select(HouseholdMember).where(
                    HouseholdMember.user_id == user_id,
                    HouseholdMember.household_id == household.id,
                )
            )
        ).scalar_one_or_none()
        if membership is not None:
            await db.delete(membership)
    await db.commit()
