"""Monthly insight (ROADMAP #18): the deterministic "what changed" aggregate, plus an optional
LLM narrative on top (aggregates in, prose out — the model never sees a raw row, §6).

The numbers are computed here and are the source of truth; the narrative (`app/services/ai/
insight.py`) is best-effort decoration. Everything is aggregated in SQL (F14) — an insight for a
backfilled month must never load that month's rows into Python.
"""

import datetime
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.budget import Budget
from app.models.category import Category
from app.models.transaction import COUNTABLE_STATUSES, Transaction
from app.rules.bands import median_cents
from app.services.ai.insight import narrate_month
from app.services.ai.llm_client import LlmClient

TRAILING_MONTHS = 6
MIN_PRIOR_MONTHS = 2  # a "vs usual" delta needs at least a couple of prior months to mean anything
TOP_MERCHANTS = 6


@dataclass(frozen=True)
class CategoryChange:
    category: str
    this_month_cents: int
    trailing_median_cents: int
    delta_cents: int  # this_month - trailing_median; positive = spent more than usual


@dataclass(frozen=True)
class BudgetVerdict:
    category: str
    actual_cents: int
    budget_cents: int
    over_cents: int  # actual - budget; positive = over budget


@dataclass(frozen=True)
class MerchantLine:
    merchant: str
    spend_cents: int
    count: int


@dataclass(frozen=True)
class MonthlyInsight:
    month: datetime.date
    income_cents: int
    spend_cents: int
    net_cents: int
    category_changes: list[CategoryChange]
    budget_verdicts: list[BudgetVerdict]
    top_merchants: list[MerchantLine]
    narrative_headline: str | None = None
    narrative_summary: str | None = None
    narrative_source: str = "unavailable"  # "llm" | "unavailable"


def _months_before(month_start: datetime.date, n: int) -> datetime.date:
    total = (month_start.year * 12 + (month_start.month - 1)) - n
    return datetime.date(total // 12, total % 12 + 1, 1)


async def build_monthly_insight_data(
    db: AsyncSession, user_id: uuid.UUID, month: datetime.date
) -> MonthlyInsight:
    """The deterministic aggregate for `month` (its first day). No LLM involved."""
    this_month = month.replace(day=1)
    window_start = _months_before(this_month, TRAILING_MONTHS)
    month_bucket = func.date_trunc("month", Transaction.date)

    # (1) income / spend / net for the target month — magnitudes for spend, signed net.
    totals = (
        await db.execute(
            select(
                func.sum(Transaction.amount).filter(Transaction.kind == "income"),
                func.sum(-Transaction.amount).filter(Transaction.kind.in_(("spend", "refund"))),
            )
            .join(Account, Transaction.account_id == Account.id)
            .where(
                Account.user_id == user_id,
                Transaction.is_split.is_(False),
                Transaction.status.in_(COUNTABLE_STATUSES),
                month_bucket == this_month,
            )
        )
    ).one()
    income = int(totals[0] or 0)
    spend = int(totals[1] or 0)

    # (2) per-(category, month) spend across the trailing window → this-month vs trailing median.
    rows = (
        await db.execute(
            select(Transaction.category_id, month_bucket.label("m"), func.sum(-Transaction.amount))
            .join(Account, Transaction.account_id == Account.id)
            .where(
                Account.user_id == user_id,
                Transaction.category_id.is_not(None),
                Transaction.kind.in_(("spend", "refund")),
                Transaction.is_split.is_(False),
                Transaction.status.in_(COUNTABLE_STATUSES),
                Transaction.date >= window_start,
            )
            .group_by(Transaction.category_id, "m")
        )
    ).all()

    this_by_cat: dict[uuid.UUID, int] = {}
    prior_by_cat: dict[uuid.UUID, list[int]] = {}
    for cat_id, bucket, cents in rows:
        bucket_month = bucket.date() if hasattr(bucket, "date") else bucket
        if bucket_month == this_month:
            this_by_cat[cat_id] = int(cents)
        else:
            prior_by_cat.setdefault(cat_id, []).append(int(cents))

    names = await _category_names(db, user_id)
    changes: list[CategoryChange] = []
    for cat_id, this_cents in this_by_cat.items():
        priors = prior_by_cat.get(cat_id, [])
        if len(priors) < MIN_PRIOR_MONTHS:
            continue
        median = int(round(median_cents([abs(a) for a in priors])))
        changes.append(
            CategoryChange(
                category=names.get(cat_id, "Uncategorized"),
                this_month_cents=this_cents,
                trailing_median_cents=median,
                delta_cents=this_cents - median,
            )
        )
    # Biggest movers first, either direction.
    changes.sort(key=lambda c: -abs(c.delta_cents))

    # (3) budget verdicts — only the categories over budget are the "what changed" signal.
    verdicts = await _budget_verdicts(db, user_id, this_month, names)

    # (4) top merchants this month, for color.
    merchants = await _top_merchants(db, user_id, this_month)

    return MonthlyInsight(
        month=this_month,
        income_cents=income,
        spend_cents=spend,
        net_cents=income - spend,
        category_changes=changes,
        budget_verdicts=verdicts,
        top_merchants=merchants,
    )


async def generate_monthly_insight(
    db: AsyncSession,
    user_id: uuid.UUID,
    month: datetime.date,
    *,
    llm_client: LlmClient | None,
) -> MonthlyInsight:
    """The aggregate plus, if an LLM is configured and responds, a narrative on top. The prose is
    strictly optional (§6): a missing model just leaves `narrative_source="unavailable"`."""
    data = await build_monthly_insight_data(db, user_id, month)
    if llm_client is None:
        return data
    narrative = await narrate_month(llm_client, _narration_payload(data))
    if narrative is None:
        return data
    return MonthlyInsight(
        **{
            **data.__dict__,
            "narrative_headline": narrative.headline,
            "narrative_summary": narrative.summary,
            "narrative_source": "llm",
        }
    )


def _narration_payload(data: MonthlyInsight) -> dict:
    """The slimmed, dollars-rounded view handed to the model — aggregates only."""
    return {
        "month": f"{data.month:%Y-%m}",
        "income": round(data.income_cents / 100, 2),
        "spend": round(data.spend_cents / 100, 2),
        "net": round(data.net_cents / 100, 2),
        "biggest_category_changes": [
            {
                "category": c.category,
                "this_month": round(c.this_month_cents / 100, 2),
                "usual_median": round(c.trailing_median_cents / 100, 2),
                "change": round(c.delta_cents / 100, 2),
            }
            for c in data.category_changes[:6]
        ],
        "over_budget": [
            {
                "category": v.category,
                "spent": round(v.actual_cents / 100, 2),
                "budget": round(v.budget_cents / 100, 2),
            }
            for v in data.budget_verdicts
        ],
        "top_merchants": [
            {"merchant": m.merchant, "spent": round(m.spend_cents / 100, 2)}
            for m in data.top_merchants[:6]
        ],
    }


async def _category_names(db: AsyncSession, user_id: uuid.UUID) -> dict[uuid.UUID, str]:
    rows = await db.execute(
        select(Category.id, Category.name).where(
            (Category.user_id == user_id) | (Category.user_id.is_(None))
        )
    )
    return {cid: name for cid, name in rows.tuples().all()}


async def _budget_verdicts(
    db: AsyncSession, user_id: uuid.UUID, month: datetime.date, names: dict[uuid.UUID, str]
) -> list[BudgetVerdict]:
    budgets = (
        (await db.execute(select(Budget).where(Budget.user_id == user_id, Budget.month == month)))
        .scalars()
        .all()
    )
    if not budgets:
        return []
    actuals = dict(
        (
            await db.execute(
                select(Transaction.category_id, func.sum(-Transaction.amount))
                .join(Account, Transaction.account_id == Account.id)
                .where(
                    Account.user_id == user_id,
                    Transaction.category_id.is_not(None),
                    Transaction.kind.in_(("spend", "refund")),
                    Transaction.is_split.is_(False),
                    Transaction.status.in_(COUNTABLE_STATUSES),
                    func.date_trunc("month", Transaction.date) == month,
                )
                .group_by(Transaction.category_id)
            )
        ).all()
    )
    verdicts = [
        BudgetVerdict(
            category=names.get(b.category_id, "Uncategorized"),
            actual_cents=int(actuals.get(b.category_id, 0)),
            budget_cents=b.amount,
            over_cents=int(actuals.get(b.category_id, 0)) - b.amount,
        )
        for b in budgets
    ]
    return sorted((v for v in verdicts if v.over_cents > 0), key=lambda v: -v.over_cents)


async def _top_merchants(
    db: AsyncSession, user_id: uuid.UUID, month: datetime.date
) -> list[MerchantLine]:
    merchant = func.coalesce(Transaction.merchant_norm, Transaction.merchant_raw)
    rows = await db.execute(
        select(merchant, func.sum(-Transaction.amount), func.count())
        .join(Account, Transaction.account_id == Account.id)
        .where(
            Account.user_id == user_id,
            Transaction.kind == "spend",
            Transaction.is_split.is_(False),
            Transaction.status.in_(COUNTABLE_STATUSES),
            func.date_trunc("month", Transaction.date) == month,
            merchant.is_not(None),
        )
        .group_by(merchant)
        .order_by(func.sum(Transaction.amount))
        .limit(TOP_MERCHANTS)
    )
    return [
        MerchantLine(merchant=m, spend_cents=int(s), count=int(c))
        for m, s, c in rows.all()
        if m and m.strip()
    ]
