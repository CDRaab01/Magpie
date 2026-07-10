"""Cash-flow calendar service (V1.md Tier 3 #23): assembles the projection inputs from the DB and
hands them to the pure `app/rules/cashflow.py`. Upcoming obligations are the account's *unmatched*
`bill_statements` (a matched bill is paid); the paycheck projection comes from the recurring-income
rules. Recent-overdue bills are included (you still owe them) within a bounded past window."""

import dataclasses
import datetime
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.account import Account
from app.models.bill_statement import BillStatement
from app.models.rule import Rule
from app.rules.bands import median_cents
from app.rules.cashflow import BillInput, classify_bills, next_paycheck_date
from app.rules.merchant_match import matches
from app.rules.recurrence import InvalidCadence, expected_next_date
from app.schemas.cashflow import CashflowCalendarOut, UpcomingBillOut
from app.services.rule_service import observation_history
from app.time_util import owner_local_date

CALENDAR_PAST_WINDOW_DAYS = 30
# How far ahead a recurring-bill rule projects its next occurrence (#24). A month-plus covers the
# gap to the next statement email without projecting far into speculative territory.
CALENDAR_PROJECT_HORIZON_DAYS = 45


async def _projected_bills(
    db: AsyncSession,
    user_id: uuid.UUID,
    today: datetime.date,
    concrete: list[BillInput],
) -> list[BillInput]:
    """Project each enabled recurring-bill rule's next occurrence into the upcoming window (#24),
    so the calendar doesn't go blank between "statement ready" emails. A projection is dropped when
    a concrete unmatched statement already covers that biller in the window (the real bill wins),
    so the two never double-count. The projected amount is the rule's observation-history median."""
    horizon = today + datetime.timedelta(days=CALENDAR_PROJECT_HORIZON_DAYS)
    rule_rows = await db.execute(
        select(Rule, Account.name)
        .join(Account, Rule.account_id == Account.id)
        .where(
            Rule.user_id == user_id,
            Rule.type == "recurring_bill",
            Rule.enabled.is_(True),
            Rule.last_matched_at.is_not(None),
        )
    )
    projected: list[BillInput] = []
    for rule, account_name in rule_rows.all():
        try:
            expected = expected_next_date(rule.last_matched_at.date(), rule.cadence or {})
        except InvalidCadence:
            continue
        if not (today <= expected <= horizon):
            continue
        # Skip if a concrete statement already stands in for this biller near the projected date.
        if any(
            matches(rule.matcher, c.biller.upper()) or matches(c.biller.upper(), rule.matcher)
            for c in concrete
        ):
            continue
        history = await observation_history(db, rule.account_id, rule.matcher)
        amounts = [abs(t.amount) for t in history if t.kind in ("spend", "transfer")]
        if not amounts:
            continue
        projected.append(
            BillInput(
                biller=rule.matcher,
                amount_due_cents=int(round(median_cents(amounts))),
                due_date=expected,
                account_name=account_name,
                is_projected=True,
            )
        )
    return projected


async def get_cashflow_calendar(
    db: AsyncSession, user_id: uuid.UUID, *, now: datetime.datetime
) -> CashflowCalendarOut:
    today = owner_local_date(now, settings.owner_timezone)

    rule_rows = await db.execute(
        select(Rule).where(
            Rule.user_id == user_id,
            Rule.type == "recurring_income",
            Rule.enabled.is_(True),
            Rule.last_matched_at.is_not(None),
        )
    )
    income_rules = [(r.last_matched_at.date(), r.cadence or {}) for r in rule_rows.scalars().all()]
    paycheck = next_paycheck_date(income_rules, today)

    since = today - datetime.timedelta(days=CALENDAR_PAST_WINDOW_DAYS)
    bill_rows = await db.execute(
        select(BillStatement, Account.name)
        .join(Account, BillStatement.account_id == Account.id)
        .where(
            Account.user_id == user_id,
            BillStatement.matched_transaction_id.is_(None),
            BillStatement.due_date >= since,
        )
    )
    bill_inputs = [
        BillInput(
            biller=bill.biller,
            amount_due_cents=bill.amount_due,
            due_date=bill.due_date,
            account_name=name,
        )
        for bill, name in bill_rows.all()
    ]

    bill_inputs += await _projected_bills(db, user_id, today, bill_inputs)
    classified = classify_bills(bill_inputs, paycheck, today)
    total_before = sum(u.amount_due_cents for u in classified if u.before_next_paycheck)
    return CashflowCalendarOut(
        next_paycheck_date=paycheck,
        total_due_before_paycheck_cents=total_before,
        bills=[UpcomingBillOut(**dataclasses.asdict(u)) for u in classified],
    )
