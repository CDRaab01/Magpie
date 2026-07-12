import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database import get_db
from app.models.merchant_tag import MerchantTag
from app.models.subscription_mute import SubscriptionMute
from app.schemas.subscription import SubscriptionOut, SubscriptionsOut
from app.security import CurrentUser
from app.services import cross_app_client
from app.services.subscription_service import (
    FITNESS_TAG,
    cost_per_visit_cents,
    list_subscriptions,
)

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])

DbSession = Annotated[AsyncSession, Depends(get_db)]

# v1 accepts only the one tag that does something (Link G). Reject others so the store stays clean.
ALLOWED_TAGS = {FITNESS_TAG}


class MuteRequest(BaseModel):
    merchant: str


class TagRequest(BaseModel):
    merchant: str
    tag: str


@router.get("", response_model=SubscriptionsOut)
async def subscriptions(current_user: CurrentUser, db: DbSession):
    """Your recurring charges, totaled and sorted by annual cost (ROADMAP #22) — the single most
    actionable screen in consumer finance. Inferred from the ledger, no rule required.

    Fitness-tagged merchants (Link G) are decorated with this month's Spotter visit count and the
    resulting cost-per-visit — best-effort, so if Spotter is quiet the row is unchanged."""
    now = datetime.datetime.now(datetime.timezone.utc)
    subs = await list_subscriptions(db, current_user.id, now=now)

    # One Spotter call for the whole screen: visits-this-month is per-user, not per-merchant. Only
    # worth it if something is actually fitness-tagged. None ⇒ Spotter didn't answer, leave rows bare.
    visits: int | None = None
    if any(FITNESS_TAG in s.tags for s in subs):
        visits = await cross_app_client.fetch_month_workout_visits(current_user.email, now=now)

    def decorate(s) -> SubscriptionOut:
        is_fitness = FITNESS_TAG in s.tags and visits is not None
        return SubscriptionOut(
            merchant=s.merchant,
            cadence=s.recurrence.cadence,
            typical_amount_cents=s.recurrence.typical_amount_cents,
            occurrences=s.recurrence.occurrences,
            last_date=s.recurrence.last_date,
            last_amount_cents=s.recurrence.last_amount_cents,
            annual_cost_cents=s.recurrence.annual_cost_cents,
            tags=sorted(s.tags),
            visits_this_month=visits if is_fitness else None,
            cost_per_visit_cents=(
                cost_per_visit_cents(s.recurrence.annual_cost_cents, visits) if is_fitness else None
            ),
        )

    return SubscriptionsOut(
        subscriptions=[decorate(s) for s in subs],
        total_annual_cost_cents=sum(s.recurrence.annual_cost_cents for s in subs),
    )


@router.post("/tag", status_code=status.HTTP_204_NO_CONTENT)
async def tag_merchant(req: TagRequest, current_user: CurrentUser, db: DbSession):
    """Tag a merchant (Link G, v1 tag "fitness") so its subscription shows cost-per-visit from
    Spotter. Idempotent (ON CONFLICT DO NOTHING); unknown tags are rejected (422)."""
    if req.tag not in ALLOWED_TAGS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"unknown tag: {req.tag}")
    stmt = (
        pg_insert(MerchantTag)
        .values(user_id=current_user.id, merchant=req.merchant, tag=req.tag)
        .on_conflict_do_nothing(constraint="uq_merchant_tag_user_merchant_tag")
    )
    await db.execute(stmt)
    await db.commit()


@router.delete("/tag", status_code=status.HTTP_204_NO_CONTENT)
async def untag_merchant(req: TagRequest, current_user: CurrentUser, db: DbSession):
    """Remove a merchant tag. No error if it wasn't tagged."""
    await db.execute(
        delete(MerchantTag).where(
            MerchantTag.user_id == current_user.id,
            MerchantTag.merchant == req.merchant,
            MerchantTag.tag == req.tag,
        )
    )
    await db.commit()


@router.post("/mute", status_code=status.HTTP_204_NO_CONTENT)
async def mute_subscription(req: MuteRequest, current_user: CurrentUser, db: DbSession):
    """Mark a merchant "not a subscription" (#12) so it drops off the screen and both subscription
    sweeps. Idempotent: muting an already-muted merchant is a no-op (ON CONFLICT DO NOTHING)."""
    stmt = (
        pg_insert(SubscriptionMute)
        .values(user_id=current_user.id, merchant=req.merchant)
        .on_conflict_do_nothing(constraint="uq_subscription_mute_user_merchant")
    )
    await db.execute(stmt)
    await db.commit()


@router.delete("/mute", status_code=status.HTTP_204_NO_CONTENT)
async def unmute_subscription(req: MuteRequest, current_user: CurrentUser, db: DbSession):
    """Un-mute a merchant — it can reappear as a subscription. No error if it wasn't muted."""
    await db.execute(
        delete(SubscriptionMute).where(
            SubscriptionMute.user_id == current_user.id,
            SubscriptionMute.merchant == req.merchant,
        )
    )
    await db.commit()


@router.get("/mutes", response_model=list[str])
async def list_muted(current_user: CurrentUser, db: DbSession) -> list[str]:
    """The merchants the owner has muted (#12) — lets the client show/undo them."""
    result = await db.execute(
        select(SubscriptionMute.merchant).where(SubscriptionMute.user_id == current_user.id)
    )
    return list(result.scalars().all())
