import datetime

from pydantic import BaseModel


class CategoryChangeOut(BaseModel):
    category: str
    this_month_cents: int
    trailing_median_cents: int
    delta_cents: int


class BudgetVerdictOut(BaseModel):
    category: str
    actual_cents: int
    budget_cents: int
    over_cents: int


class MerchantLineOut(BaseModel):
    merchant: str
    spend_cents: int
    count: int


class MonthlyInsightOut(BaseModel):
    month: datetime.date
    income_cents: int
    spend_cents: int
    net_cents: int
    category_changes: list[CategoryChangeOut]
    budget_verdicts: list[BudgetVerdictOut]
    top_merchants: list[MerchantLineOut]
    narrative_headline: str | None
    narrative_summary: str | None
    narrative_source: str  # "llm" | "unavailable"
