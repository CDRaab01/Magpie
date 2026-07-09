import datetime

from pydantic import BaseModel


class UpcomingBillOut(BaseModel):
    biller: str
    amount_due_cents: int
    due_date: datetime.date
    account_name: str
    is_overdue: bool
    before_next_paycheck: bool


class CashflowCalendarOut(BaseModel):
    """The "due before next paycheck" calendar (V1.md Tier 3 #23)."""

    next_paycheck_date: datetime.date | None
    total_due_before_paycheck_cents: int
    bills: list[UpcomingBillOut]
