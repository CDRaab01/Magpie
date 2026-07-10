import datetime

from pydantic import BaseModel


class SubscriptionOut(BaseModel):
    merchant: str
    cadence: str
    typical_amount_cents: int
    occurrences: int
    last_date: datetime.date
    last_amount_cents: int
    annual_cost_cents: int


class SubscriptionsOut(BaseModel):
    subscriptions: list[SubscriptionOut]
    total_annual_cost_cents: int
