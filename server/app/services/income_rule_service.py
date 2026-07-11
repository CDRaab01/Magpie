"""Seed recurring-income rules from deposit history (ROADMAP #1). Arms paycheck-late/short,
next-paycheck-date, and the real safe-to-spend — none of which fire today because prod has zero
`recurring_income` rules.

Detection is pure (`app/rules/recurring.py`); this applies the two guards that need the DB and the
clock: a **recency gate** (a former employer whose last deposit is old must NOT become a live
"late paycheck" alert — this is the arming trap) and an **amount floor** (a paycheck/rent is a
meaningful sum, not a $8 interest credit). Proposals are drafts the owner confirms; seeding
anchors each rule's `last_matched_at` to its latest deposit so paycheck-late computes the *next*
expected date rather than pinging about a paycheck that already arrived.
"""

import datetime
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.rule import Rule
from app.models.transaction import COUNTABLE_STATUSES, Transaction
from app.rules.recurring import RecurringShape, detect_recurring
from app.rules.merchant_match import matches, normalize_merchant

LOOKBACK_DAYS = 500
RECENCY_DAYS = 45  # the latest deposit must be within this window, or the income stream is dormant
FLOOR_CENTS = 50000  # $500 — below this it's a fee waiver / interest / small transfer, not income


@dataclass(frozen=True)
class IncomeProposal:
    merchant: str
    shape: RecurringShape


async def propose_income_rules(
    db: AsyncSession, user_id: uuid.UUID, *, now: datetime.datetime
) -> list[IncomeProposal]:
    """Income streams that look like a live paycheck/rent and have no rule yet, richest first."""
    today = now.date()
    merchant = func.coalesce(Transaction.merchant_norm, Transaction.merchant_raw)
    rows = (
        await db.execute(
            select(merchant, Transaction.date, Transaction.amount)
            .join(Account, Transaction.account_id == Account.id)
            .where(
                Account.user_id == user_id,
                Transaction.kind == "income",
                Transaction.split_parent_id.is_(None),
                Transaction.status.in_(COUNTABLE_STATUSES),
                Transaction.date >= today - datetime.timedelta(days=LOOKBACK_DAYS),
                merchant.is_not(None),
            )
            .order_by(merchant, Transaction.date)
        )
    ).all()

    by_merchant: dict[str, list[tuple[datetime.date, int]]] = {}
    for name, date, amount in rows:
        if name and name.strip():
            by_merchant.setdefault(name, []).append((date, amount))

    existing = {
        r.matcher
        for r in (
            await db.execute(
                select(Rule).where(Rule.user_id == user_id, Rule.type == "recurring_income")
            )
        )
        .scalars()
        .all()
    }

    proposals: list[IncomeProposal] = []
    for name, dated_amounts in by_merchant.items():
        shape = detect_recurring(dated_amounts)
        if shape is None:
            continue
        if shape.typical_amount_cents < FLOOR_CENTS:
            continue  # fee/interest/small transfer, not a paycheck
        if (today - shape.last_date).days > RECENCY_DAYS:
            continue  # dormant stream (a former employer) — arming it would false-alarm "late"
        matcher = normalize_merchant(name)
        if not matcher or any(matches(m, matcher) or matches(matcher, m) for m in existing):
            continue
        proposals.append(IncomeProposal(merchant=matcher, shape=shape))

    proposals.sort(key=lambda p: -p.shape.typical_amount_cents)
    return proposals


@dataclass(frozen=True)
class SeedSummary:
    dry_run: bool
    rules_created: int
    proposals: list[IncomeProposal]


async def seed_income_rules(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    dry_run: bool = True,
    only: set[str] | None = None,
    now: datetime.datetime,
) -> SeedSummary:
    """Create a `recurring_income` rule per proposal (or only those whose matcher is in `only` —
    per-proposal selection, because not every detected stream is one to arm: a former employer's
    recency-passing deposits, or temporary leave pay, should be left out). `last_matched_at` is
    anchored to the latest deposit so paycheck-late starts from reality. `dry_run` rolls back."""
    proposals = await propose_income_rules(db, user_id, now=now)
    chosen = [p for p in proposals if only is None or p.merchant in only]
    for p in chosen:
        db.add(
            Rule(
                user_id=user_id,
                type="recurring_income",
                account_id=None,  # income can land on any account; matched by merchant
                matcher=p.merchant,
                cadence={"kind": p.shape.cadence, "slack_days": p.shape.slack_days},
                amount_band={"pct": p.shape.band_pct},
                category_id=None,
                last_matched_at=datetime.datetime.combine(
                    p.shape.last_date, datetime.time(), datetime.timezone.utc
                ),
                enabled=True,
            )
        )
    if dry_run:
        await db.rollback()
    else:
        await db.commit()
    return SeedSummary(dry_run=dry_run, rules_created=len(chosen), proposals=proposals)
