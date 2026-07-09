"""Read-model schemas for the analytics/chart surfaces (ROADMAP.md Wave 1). All amounts are
signed integer cents (spend negative), the suite-wide convention — the client formats them."""

import datetime

from pydantic import BaseModel


class MonthSummaryOut(BaseModel):
    year: int
    month: int
    income_cents: int
    spend_cents: int  # signed (negative); refunds already netted in
    net_cents: int


class HistoryOut(BaseModel):
    """The last N months of income/spend/net, oldest first — a left-to-right chart series."""

    months: list[MonthSummaryOut]


class CategorySummaryItem(BaseModel):
    category_id: str | None  # None = uncategorized spend
    category_name: str
    spend_cents: int  # signed (negative); the category's net spend for the month


class CategorySummaryOut(BaseModel):
    month: datetime.date
    categories: list[CategorySummaryItem]  # largest spend first


class MerchantSummaryItem(BaseModel):
    merchant: str
    spend_cents: int  # signed (negative)
    transaction_count: int


class MerchantSummaryOut(BaseModel):
    month: datetime.date
    merchants: list[MerchantSummaryItem]  # largest spend first


class SafeToSpendOut(BaseModel):
    """The genre's headline number (Simple bank's "Safe-to-Spend"): what's left in the
    depository accounts after the bills due before the next paycheck are set aside."""

    safe_to_spend_cents: int
    depository_balance_cents: int
    due_before_paycheck_cents: int
    next_paycheck_date: datetime.date | None
