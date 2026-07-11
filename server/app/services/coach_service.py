"""AI budget coach (owner-requested, 2026-07-11): goal CRUD, month-progress status over the FULL
budget table, per-category deep-dive analysis, and the "what would need to change" savings plan.

Everything here is deterministic — the math lives in the pure `app/rules/pace.py`, this module
feeds it SQL aggregates. The LLM layer (Stage 3, `ai/coach.py`) only phrases these numbers.

Projection honesty (the household's real shape):
- Income median is **3 months**, not 6: the household is on parental leave right now, and a long
  income median would keep projecting pre-leave paychecks. Three months adapts within a quarter.
- Spend median stays 6 months (same window the monthly insight uses).
- `uncategorized_mtd_cents` is surfaced, never hidden — spend without a category is invisible to
  per-category pace, and the coach should say so rather than coach on incomplete numbers.
- "Fixed" categories (rent, utilities) are detected by **bill share** — the armed recurring_bill
  rules carry category_id=None, so the honest signal is: >50% of the category's trailing spend
  comes from merchants matching an enabled bill rule. Fixed categories are never proposed as cuts.
"""

import datetime
import uuid
from calendar import monthrange

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.account import Account
from app.models.budget import Budget
from app.models.category import Category
from app.models.goal import Goal
from app.models.rule import Rule
from app.models.transaction import COUNTABLE_STATUSES, Transaction
from app.rules.bands import median_cents
from app.rules.merchant_match import matches
from app.rules.pace import (
    CategoryPace,
    CutCandidate,
    PlanResult,
    category_pace,
    plan_category_cuts,
    project_net,
)
from app.schemas.coach import (
    BudgetHistoryOut,
    BudgetPaceOut,
    CategoryAnalysisOut,
    CoachPlanOut,
    CoachStatusOut,
    GoalOut,
    MerchantLineOut,
    MonthSpendOut,
    NetProjectionOut,
    ProposedCutOut,
)
from app.services.budget_service import (
    actual_spend_by_category,
    category_names,
    list_budgets,
    median_spend_by_category,
    monthly_spend_by_category,
)
from app.services.summary_service import spending_history, top_merchants
from app.time_util import owner_local_date

INCOME_MEDIAN_MONTHS = 3  # leave-adaptive: a long median keeps projecting paused paychecks
SPEND_MEDIAN_MONTHS = 6  # same trailing window the monthly insight uses
BILL_SHARE_FIXED_THRESHOLD = 0.5  # a category is "fixed" when bills dominate its spend


# --- goal CRUD ------------------------------------------------------------------------------


async def get_goal(db: AsyncSession, user_id: uuid.UUID) -> Goal | None:
    result = await db.execute(
        select(Goal).where(
            Goal.user_id == user_id, Goal.kind == "monthly_savings", Goal.active.is_(True)
        )
    )
    return result.scalar_one_or_none()


async def upsert_goal(db: AsyncSession, user_id: uuid.UUID, amount_cents: int) -> Goal:
    """One active savings goal per user: update it in place if it exists, else create it."""
    goal = await get_goal(db, user_id)
    if goal is None:
        goal = Goal(user_id=user_id, kind="monthly_savings", amount_cents=amount_cents)
        db.add(goal)
    else:
        goal.amount_cents = amount_cents
    await db.commit()
    await db.refresh(goal)
    return goal


async def clear_goal(db: AsyncSession, user_id: uuid.UUID) -> None:
    goal = await get_goal(db, user_id)
    if goal is not None:
        goal.active = False
        await db.commit()


def _goal_out(goal: Goal | None) -> GoalOut | None:
    if goal is None:
        return None
    return GoalOut(
        id=goal.id, kind=goal.kind, amount_cents=goal.amount_cents, created_at=goal.created_at
    )


# --- shared aggregates ----------------------------------------------------------------------


async def _uncategorized_mtd_cents(
    db: AsyncSession, user_id: uuid.UUID, month_start: datetime.date, today: datetime.date
) -> int:
    """MTD spend magnitude with no category — the pace math's honest blind spot."""
    result = await db.execute(
        select(func.coalesce(func.sum(-Transaction.amount), 0))
        .join(Account, Transaction.account_id == Account.id)
        .where(
            Account.user_id == user_id,
            Transaction.category_id.is_(None),
            Transaction.kind.in_(("spend", "refund")),
            Transaction.is_split.is_(False),
            Transaction.status.in_(COUNTABLE_STATUSES),
            Transaction.date >= month_start,
            Transaction.date <= today,
        )
    )
    return max(0, int(result.scalar_one()))


async def _fixed_categories(
    db: AsyncSession, user_id: uuid.UUID, this_month: datetime.date
) -> set[uuid.UUID]:
    """Categories whose trailing spend is bill-dominated (>50% from merchants matching an enabled
    recurring_bill rule) — rent and utilities are obligations, not coaching targets. Matcher-based
    because the armed bill rules deliberately carry category_id=None."""
    matchers = [
        r.matcher
        for r in (
            await db.execute(
                select(Rule).where(
                    Rule.user_id == user_id,
                    Rule.type == "recurring_bill",
                    Rule.enabled.is_(True),
                )
            )
        )
        .scalars()
        .all()
    ]
    if not matchers:
        return set()

    total = this_month.year * 12 + (this_month.month - 1)
    window_start = datetime.date(
        (total - SPEND_MEDIAN_MONTHS) // 12, (total - SPEND_MEDIAN_MONTHS) % 12 + 1, 1
    )
    merchant = func.coalesce(Transaction.merchant_norm, Transaction.merchant_raw)
    rows = (
        await db.execute(
            select(Transaction.category_id, merchant, func.sum(-Transaction.amount))
            .join(Account, Transaction.account_id == Account.id)
            .where(
                Account.user_id == user_id,
                Transaction.category_id.is_not(None),
                Transaction.kind.in_(("spend", "refund")),
                Transaction.is_split.is_(False),
                Transaction.status.in_(COUNTABLE_STATUSES),
                Transaction.date >= window_start,
                Transaction.date < this_month,
            )
            .group_by(Transaction.category_id, merchant)
        )
    ).all()

    totals: dict[uuid.UUID, int] = {}
    bill_spend: dict[uuid.UUID, int] = {}
    for cat_id, name, spend in rows:
        amount = abs(int(spend))
        totals[cat_id] = totals.get(cat_id, 0) + amount
        if name and any(matches(m, name.upper()) or matches(name.upper(), m) for m in matchers):
            bill_spend[cat_id] = bill_spend.get(cat_id, 0) + amount

    return {
        cat_id
        for cat_id, total_spend in totals.items()
        if total_spend > 0 and bill_spend.get(cat_id, 0) / total_spend > BILL_SHARE_FIXED_THRESHOLD
    }


async def _income_spend_medians(
    db: AsyncSession, user_id: uuid.UUID, *, now: datetime.datetime
) -> tuple[int, int, int, int]:
    """(mtd_income, mtd_spend, median_income_3mo, median_spend_6mo), magnitudes positive.
    One spending_history call covers both the MTD month and the trailing windows.

    The series is zero-filled per month; months BEFORE the ledger's history began are "no data",
    not "zero spend" — counting them would drag a young ledger's medians toward zero and make
    every projection optimistic. Slice the priors from the first month with any activity."""
    history = await spending_history(db, user_id, months=SPEND_MEDIAN_MONTHS + 1, now=now)
    if not history:
        return 0, 0, 0, 0
    current = history[-1]
    priors = history[:-1]
    mtd_income = max(0, current.income_cents)
    mtd_spend = abs(current.spend_cents)
    first_active = next(
        (i for i, m in enumerate(priors) if m.income_cents != 0 or m.spend_cents != 0),
        len(priors),
    )
    priors = priors[first_active:]
    income_priors = [max(0, m.income_cents) for m in priors[-INCOME_MEDIAN_MONTHS:]]
    spend_priors = [abs(m.spend_cents) for m in priors]
    median_income = int(round(median_cents(income_priors))) if income_priors else 0
    median_spend = int(round(median_cents(spend_priors))) if spend_priors else 0
    return mtd_income, mtd_spend, median_income, median_spend


def _month_frame(now: datetime.datetime) -> tuple[datetime.date, datetime.date, int, int]:
    today = owner_local_date(now, settings.owner_timezone)
    this_month = today.replace(day=1)
    return today, this_month, today.day, monthrange(today.year, today.month)[1]


def _pace_out(
    budget: Budget,
    name: str,
    pace: CategoryPace,
    trailing_median: int,
) -> BudgetPaceOut:
    reference = pace.projected_cents if pace.projected_cents is not None else pace.spent_cents
    return BudgetPaceOut(
        budget_id=budget.id,
        category_id=budget.category_id,
        category_name=name,
        budget_cents=pace.budget_cents,
        spent_cents=pace.spent_cents,
        projected_cents=pace.projected_cents,
        remaining_cents=pace.remaining_cents,
        daily_allowance_cents=pace.daily_allowance_cents,
        status=pace.status,
        trailing_median_cents=trailing_median,
        delta_vs_usual_cents=reference - trailing_median,
    )


# --- status ---------------------------------------------------------------------------------


async def build_coach_status(
    db: AsyncSession, user_id: uuid.UUID, *, now: datetime.datetime
) -> CoachStatusOut:
    """The whole month at a glance: every budgeted category's pace + vs-usual context (the FULL
    table — the AI analyzes all of it, never a top-N), the net projection, and the goal delta."""
    today, this_month, elapsed, total_days = _month_frame(now)

    budgets = await list_budgets(db, user_id, this_month)
    actual = await actual_spend_by_category(db, user_id, this_month)
    medians = await median_spend_by_category(db, user_id, this_month, months=SPEND_MEDIAN_MONTHS)
    names = await category_names(db, user_id)

    rows = []
    for budget in budgets:
        spent = max(0, -actual.get(budget.category_id, 0))
        pace = category_pace(
            budget.amount, spent, elapsed, total_days, watch_factor=settings.coach_pace_factor
        )
        rows.append(
            _pace_out(
                budget,
                names.get(budget.category_id, "Uncategorized"),
                pace,
                medians.get(budget.category_id, 0),
            )
        )
    # Worst first: the order the coach (and the owner) should read them in.
    severity = {"over": 0, "over_pace": 1, "watch": 2, "on_track": 3, "early": 4}
    rows.sort(key=lambda r: (severity.get(r.status, 5), -r.delta_vs_usual_cents))

    mtd_income, mtd_spend, median_income, median_spend = await _income_spend_medians(
        db, user_id, now=now
    )
    net = project_net(
        mtd_income_cents=mtd_income,
        mtd_spend_cents=mtd_spend,
        median_income_cents=median_income,
        median_spend_cents=median_spend,
        elapsed_days=elapsed,
        total_days=total_days,
    )
    goal = await get_goal(db, user_id)
    return CoachStatusOut(
        month=this_month,
        days_elapsed=elapsed,
        days_in_month=total_days,
        budgets=rows,
        goal=_goal_out(goal),
        net=NetProjectionOut(
            mtd_income_cents=mtd_income,
            mtd_spend_cents=mtd_spend,
            projected_income_cents=net.projected_income_cents,
            projected_spend_cents=net.projected_spend_cents,
            projected_net_cents=net.projected_net_cents,
            basis=net.basis,
            goal_delta_cents=(
                net.projected_net_cents - goal.amount_cents if goal is not None else None
            ),
        ),
        uncategorized_mtd_cents=await _uncategorized_mtd_cents(db, user_id, this_month, today),
    )


# --- per-category deep dive -----------------------------------------------------------------


async def build_category_analysis(
    db: AsyncSession, user_id: uuid.UUID, category_id: uuid.UUID, *, now: datetime.datetime
) -> CategoryAnalysisOut:
    """One category in depth (budgeted or not): 6-month trend, vs-usual, budget history, and
    where the money went this month — the aggregate the AI's per-category analysis is grounded in."""
    category = (
        await db.execute(
            select(Category).where(
                Category.id == category_id,
                (Category.user_id == user_id) | (Category.user_id.is_(None)),
            )
        )
    ).scalar_one_or_none()
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")

    today, this_month, elapsed, total_days = _month_frame(now)

    actual = await actual_spend_by_category(db, user_id, this_month)
    spent = max(0, -actual.get(category_id, 0))

    history_by_cat = await monthly_spend_by_category(
        db, user_id, this_month, months=SPEND_MEDIAN_MONTHS
    )
    history = [(m, abs(a)) for m, a in history_by_cat.get(category_id, [])]
    trailing_median = int(round(median_cents([a for _m, a in history]))) if history else 0

    budget = next(
        (b for b in await list_budgets(db, user_id, this_month) if b.category_id == category_id),
        None,
    )
    pace_row = None
    if budget is not None:
        pace = category_pace(
            budget.amount, spent, elapsed, total_days, watch_factor=settings.coach_pace_factor
        )
        pace_row = _pace_out(budget, category.name, pace, trailing_median)

    # Budget-vs-actual for the months that had a budget (owner-scoped; oldest first).
    prior_budgets = (
        (
            await db.execute(
                select(Budget)
                .where(
                    Budget.user_id == user_id,
                    Budget.category_id == category_id,
                    Budget.month < this_month,
                )
                .order_by(Budget.month)
            )
        )
        .scalars()
        .all()
    )
    spend_by_month = dict(history)
    budget_history = [
        BudgetHistoryOut(
            month=b.month, budget_cents=b.amount, actual_cents=spend_by_month.get(b.month, 0)
        )
        for b in prior_budgets[-SPEND_MEDIAN_MONTHS:]
    ]

    merchants = await top_merchants(db, user_id, this_month, category_id=category_id, limit=6)

    return CategoryAnalysisOut(
        category_id=category_id,
        category_name=category.name,
        month=this_month,
        budget_cents=budget.amount if budget is not None else None,
        spent_cents=spent,
        pace=pace_row,
        monthly_history=[MonthSpendOut(month=m, spend_cents=a) for m, a in history],
        trailing_median_cents=trailing_median,
        budget_history=budget_history,
        top_merchants=[
            MerchantLineOut(merchant=m, spend_cents=abs(s), count=c) for m, s, c in merchants
        ],
    )


# --- savings plan ---------------------------------------------------------------------------


async def build_savings_plan(
    db: AsyncSession, user_id: uuid.UUID, target_cents: int, *, now: datetime.datetime
) -> CoachPlanOut:
    """ "What would need to change" to save `target_cents` a month — pure computation, never
    stored. Baselines are the owner's own budgets where set, else trailing medians; bill-dominated
    categories are untouchable; a cut never dips below what's already spent this month."""
    _today, this_month, _elapsed, _total_days = _month_frame(now)

    mtd_income, mtd_spend, median_income, median_spend = await _income_spend_medians(
        db, user_id, now=now
    )
    baseline_net = median_income - median_spend
    needed = target_cents - baseline_net

    budgets = {b.category_id: b for b in await list_budgets(db, user_id, this_month)}
    medians = await median_spend_by_category(db, user_id, this_month, months=3)
    actual = await actual_spend_by_category(db, user_id, this_month)
    names = await category_names(db, user_id)
    fixed = await _fixed_categories(db, user_id, this_month)

    candidates = []
    for cat_id in set(medians) | set(budgets):
        budget = budgets.get(cat_id)
        baseline = budget.amount if budget is not None else medians.get(cat_id, 0)
        if baseline <= 0:
            continue
        candidates.append(
            CutCandidate(
                category_id=cat_id,
                category_name=names.get(cat_id, "Uncategorized"),
                budget_id=budget.id if budget is not None else None,
                baseline_cents=baseline,
                spent_cents=max(0, -actual.get(cat_id, 0)),
                fixed=cat_id in fixed,
            )
        )

    result: PlanResult = plan_category_cuts(candidates, needed)
    return CoachPlanOut(
        target_cents=target_cents,
        baseline_net_cents=baseline_net,
        needed_cents=needed,
        achievable_cents=result.achievable_cents,
        shortfall_cents=result.shortfall_cents,
        cuts=[
            ProposedCutOut(
                category_id=c.category_id,
                category_name=c.category_name,
                budget_id=c.budget_id,
                from_cents=c.from_cents,
                to_cents=c.to_cents,
                cut_cents=c.cut_cents,
            )
            for c in result.cuts
        ],
    )
