"""Seed recurring-bill rules from spend history (ROADMAP #2). Arms the projected cash-flow
calendar (#24), auto-fills recurring bill payments as they land, and (with the recurring-bill-late
sweep) pages when a bill's expected payment doesn't show.

The sibling of `income_rule_service`, sharing the `detect_recurring` detector — a bill's timing is
regular and its amount can swing seasonally (utilities), so the band is derived from the data.
Two differences from income: a bill is bound to **one payment rail** (CLAUDE.md §2), so each rule
carries the `account_id` it's usually paid from; and there's no amount floor (a $16 subscription is
a real recurring charge). The recency gate is the same and load-bearing — a prior residence's
utilities (the Ohio accounts in the real ledger) are dormant and must not arm a "bill missing"
alert.
"""

import datetime
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.rule import Rule
from app.models.transaction import COUNTABLE_STATUSES, Transaction
from app.rules.merchant_match import matches, normalize_merchant
from app.rules.recurring import RecurringShape, detect_recurring

LOOKBACK_DAYS = 500
RECENCY_DAYS = 45  # the latest payment must be within this window, or the biller is dormant


@dataclass(frozen=True)
class BillProposal:
    merchant: str
    account_id: uuid.UUID
    account_name: str
    shape: RecurringShape


async def propose_bill_rules(
    db: AsyncSession, user_id: uuid.UUID, *, now: datetime.datetime
) -> list[BillProposal]:
    """Bill-shaped spend recurrences that are still live and have no rule yet, largest first."""
    today = now.date()
    merchant = func.coalesce(Transaction.merchant_norm, Transaction.merchant_raw)
    rows = (
        await db.execute(
            select(merchant, Transaction.account_id, Transaction.date, Transaction.amount)
            .join(Account, Transaction.account_id == Account.id)
            .where(
                Account.user_id == user_id,
                Transaction.kind == "spend",
                Transaction.split_parent_id.is_(None),
                Transaction.status.in_(COUNTABLE_STATUSES),
                Transaction.date >= today - datetime.timedelta(days=LOOKBACK_DAYS),
                merchant.is_not(None),
            )
        )
    ).all()

    # Per merchant: the (date, amount) history, plus a tally of which account pays it (the rail).
    history: dict[str, list[tuple[datetime.date, int]]] = {}
    rail_tally: dict[str, dict[uuid.UUID, int]] = {}
    for name, account_id, date, amount in rows:
        if not name or not name.strip():
            continue
        history.setdefault(name, []).append((date, amount))
        rail_tally.setdefault(name, {})[account_id] = (
            rail_tally.get(name, {}).get(account_id, 0) + 1
        )

    names = dict(
        (aid, aname)
        for aid, aname in (
            await db.execute(select(Account.id, Account.name).where(Account.user_id == user_id))
        ).tuples()
    )
    existing = {
        r.matcher
        for r in (
            await db.execute(
                select(Rule).where(Rule.user_id == user_id, Rule.type == "recurring_bill")
            )
        )
        .scalars()
        .all()
    }

    proposals: list[BillProposal] = []
    for name, dated_amounts in history.items():
        shape = detect_recurring(dated_amounts)
        if shape is None:
            continue
        if (today - shape.last_date).days > RECENCY_DAYS:
            continue  # dormant biller (a former residence's utility) — arming would false-alarm
        matcher = normalize_merchant(name)
        if not matcher or any(matches(m, matcher) or matches(matcher, m) for m in existing):
            continue
        rail = max(rail_tally[name].items(), key=lambda kv: kv[1])[
            0
        ]  # the account it's usually paid from
        proposals.append(
            BillProposal(
                merchant=matcher,
                account_id=rail,
                account_name=names.get(rail, "?"),
                shape=shape,
            )
        )
    proposals.sort(key=lambda p: -p.shape.typical_amount_cents)
    return proposals


@dataclass(frozen=True)
class BillSeedSummary:
    dry_run: bool
    rules_created: int
    proposals: list[BillProposal]


async def seed_bill_rules(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    dry_run: bool = True,
    only: set[str] | None = None,
    now: datetime.datetime,
) -> BillSeedSummary:
    """Create a `recurring_bill` rule per proposal (or only those whose matcher is in `only` — the
    per-proposal selection the owner needs, since not every detected recurrence is one they want
    armed). `last_matched_at` anchors to the latest payment; `account_id` is the payment rail."""
    proposals = await propose_bill_rules(db, user_id, now=now)
    chosen = [p for p in proposals if only is None or p.merchant in only]
    for p in chosen:
        db.add(
            Rule(
                user_id=user_id,
                type="recurring_bill",
                account_id=p.account_id,
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
    return BillSeedSummary(dry_run=dry_run, rules_created=len(chosen), proposals=proposals)
