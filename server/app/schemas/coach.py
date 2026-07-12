"""AI budget coach schemas: goal CRUD, month-progress status (the FULL budget table with
per-category analysis context — never a truncated top-N), the per-category deep-dive, and the
savings plan (cuts as drafts; nothing here is ever persisted by the server on the model's say-so).
"""

import datetime
import uuid

from pydantic import BaseModel, Field


class GoalUpsert(BaseModel):
    amount_cents: int = Field(gt=0)  # monthly savings target: net >= this


class GoalOut(BaseModel):
    id: uuid.UUID
    kind: str
    amount_cents: int
    created_at: datetime.datetime


class BudgetPaceOut(BaseModel):
    """One budgeted category's full analysis context — pace AND how this month compares to the
    category's own history, so the AI can analyze the whole table or any single row."""

    budget_id: uuid.UUID
    category_id: uuid.UUID
    category_name: str
    budget_cents: int
    spent_cents: int  # MTD magnitude
    projected_cents: int | None  # None while "early"
    remaining_cents: int
    daily_allowance_cents: int
    status: str  # early | on_track | watch | over_pace | over
    trailing_median_cents: int  # this category's own 6-mo median monthly spend
    delta_vs_usual_cents: int  # (projected or spent) - median; positive = trending above usual


class NetProjectionOut(BaseModel):
    mtd_income_cents: int
    mtd_spend_cents: int
    projected_income_cents: int  # max(MTD, 3-mo median) — never extrapolated
    projected_spend_cents: int  # elapsed-weighted blend of linear and 6-mo median
    projected_net_cents: int
    basis: str  # "blend" | "mtd_only"
    goal_delta_cents: int | None  # projected_net - goal; None without an active goal


class CoachStatusOut(BaseModel):
    month: datetime.date
    days_elapsed: int
    days_in_month: int
    budgets: list[BudgetPaceOut]  # EVERY budgeted category — the full table
    goal: GoalOut | None
    net: NetProjectionOut
    # Coaching accuracy is honest: spend the pace math can't see because it has no category.
    uncategorized_mtd_cents: int
    # Federated awareness Link A (reported by Cookbook): home-cooked meals, last 14 days vs the
    # prior 14. None means "Cookbook didn't say" (integration off / unreachable) — never zero.
    cooked_meals_last_14d: int | None = None
    cooked_meals_prior_14d: int | None = None
    narrative_headline: str | None = None
    narrative_coaching: str | None = None
    narrative_source: str = "unavailable"  # "llm" | "unavailable"


class MonthSpendOut(BaseModel):
    month: datetime.date
    spend_cents: int


class BudgetHistoryOut(BaseModel):
    month: datetime.date
    budget_cents: int
    actual_cents: int


class MerchantLineOut(BaseModel):
    merchant: str
    spend_cents: int
    count: int


class CategoryAnalysisOut(BaseModel):
    """Deep-dive on one category (budgeted or not): trend, vs-usual, where the money went."""

    category_id: uuid.UUID
    category_name: str
    month: datetime.date
    budget_cents: int | None  # None when un-budgeted this month
    spent_cents: int  # MTD magnitude
    pace: BudgetPaceOut | None  # None when un-budgeted
    monthly_history: list[MonthSpendOut]  # last 6 full months, oldest first
    trailing_median_cents: int
    budget_history: list[BudgetHistoryOut]  # months that had a budget, oldest first
    top_merchants: list[MerchantLineOut]  # this month, largest spend first
    narrative_headline: str | None = None
    narrative_coaching: str | None = None
    narrative_source: str = "unavailable"


class ProposedCutOut(BaseModel):
    category_id: uuid.UUID
    category_name: str
    budget_id: uuid.UUID | None  # PATCH this budget when set, else POST a new one
    from_cents: int
    to_cents: int
    cut_cents: int


class CoachPlanOut(BaseModel):
    """ "What would need to change" for a monthly savings target — computed, never stored.
    Accepting a cut is the owner PATCHing/POSTing the budget; shortfall is reported honestly."""

    target_cents: int
    baseline_net_cents: int  # trailing medians: income - spend
    needed_cents: int  # target - baseline_net (<= 0 means already on target)
    achievable_cents: int
    shortfall_cents: int
    cuts: list[ProposedCutOut]
    narrative_headline: str | None = None
    narrative_coaching: str | None = None
    narrative_source: str = "unavailable"
