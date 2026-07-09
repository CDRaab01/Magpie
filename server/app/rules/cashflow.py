"""Cash-flow calendar projection (V1.md Tier 3 #23) — pure, no I/O. Answers the app's headline
question, "what's due before my next paycheck?": project the next paycheck date from the
recurring-income rules, then flag each upcoming bill as landing before or after it.

Kept in `app/rules/` (the pure math package) so the client only displays — CLAUDE.md's "ledger/
rules math centralized and pure; clients display, never compute".
"""

import datetime
from dataclasses import dataclass

from app.rules.recurrence import InvalidCadence, expected_next_date


@dataclass(frozen=True)
class BillInput:
    biller: str
    amount_due_cents: int
    due_date: datetime.date
    account_name: str


@dataclass(frozen=True)
class UpcomingBill:
    biller: str
    amount_due_cents: int
    due_date: datetime.date
    account_name: str
    is_overdue: bool
    before_next_paycheck: bool


def next_paycheck_date(
    income_rules: list[tuple[datetime.date, dict]], today: datetime.date
) -> datetime.date | None:
    """The soonest expected paycheck across the recurring-income rules. Each rule contributes its
    `expected_next_date(last_matched, cadence)`; the projection is the earliest of those. A rule
    already overdue still contributes its (past) expected date — the paycheck it's still waiting on
    is the next one to arrive. Returns None when there are no usable income rules."""
    dates: list[datetime.date] = []
    for last_matched, cadence in income_rules:
        try:
            dates.append(expected_next_date(last_matched, cadence))
        except InvalidCadence:
            continue  # a malformed cadence is a rule-editor problem, not a projection error
    return min(dates) if dates else None


def classify_bills(
    bills: list[BillInput], next_paycheck: datetime.date | None, today: datetime.date
) -> list[UpcomingBill]:
    """Sort bills by due date and flag each: overdue (due before today) and whether it falls on or
    before the next paycheck (the "handle these first" set). With no paycheck projection, nothing
    is `before_next_paycheck` — the calendar still lists the bills, just without the divider."""
    result: list[UpcomingBill] = []
    for bill in sorted(bills, key=lambda b: b.due_date):
        result.append(
            UpcomingBill(
                biller=bill.biller,
                amount_due_cents=bill.amount_due_cents,
                due_date=bill.due_date,
                account_name=bill.account_name,
                is_overdue=bill.due_date < today,
                before_next_paycheck=next_paycheck is not None and bill.due_date <= next_paycheck,
            )
        )
    return result
