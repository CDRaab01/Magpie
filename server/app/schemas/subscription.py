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
    # User tags on this merchant (Link G). v1: "fitness".
    tags: list[str] = []
    # Cross-app decoration for fitness-tagged merchants, from Spotter (Link G). Both None when the
    # merchant isn't fitness-tagged or Spotter didn't answer; visits present with cost None means
    # tagged but 0 visits this month (paying, not going).
    visits_this_month: int | None = None
    cost_per_visit_cents: int | None = None


class SubscriptionsOut(BaseModel):
    subscriptions: list[SubscriptionOut]
    total_annual_cost_cents: int
