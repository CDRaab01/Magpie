import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.subscription import SubscriptionOut, SubscriptionsOut
from app.security import CurrentUser
from app.services.subscription_service import list_subscriptions

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


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
