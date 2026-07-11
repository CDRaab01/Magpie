import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database import get_db
from app.models.subscription_mute import SubscriptionMute
from app.schemas.subscription import SubscriptionOut, SubscriptionsOut
from app.security import CurrentUser
from app.services.subscription_service import list_subscriptions

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


class MuteRequest(BaseModel):
    merchant: str


@router.get("", response_model=SubscriptionsOut)
async def subscriptions(current_user: CurrentUser, db: DbSession):
    """Your recurring charges, totaled and sorted by annual cost (ROADMAP #22) — the single most
    actionable screen in consumer finance. Inferred from the ledger, no rule required."""
    now = datetime.datetime.now(datetime.timezone.utc)
    subs = await list_subscriptions(db, current_user.id, now=now)
    return SubscriptionsOut(
        subscriptions=[
            SubscriptionOut(
                merchant=s.merchant,
                cadence=s.recurrence.cadence,
                typical_amount_cents=s.recurrence.typical_amount_cents,
                occurrences=s.recurrence.occurrences,
                last_date=s.recurrence.last_date,
                last_amount_cents=s.recurrence.last_amount_cents,
                annual_cost_cents=s.recurrence.annual_cost_cents,
            )
            for s in subs
        ],
        total_annual_cost_cents=sum(s.recurrence.annual_cost_cents for s in subs),
    )


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
