"""Budget pace + savings-plan math (AI budget coach) — pure, no I/O.

The coach's awareness is deterministic: these functions compute month-progress pace per budgeted
category, a projected month-end net, and a greedy savings plan. The LLM layer only *phrases* what
this module computes — it never does arithmetic (house style: `app/rules/` judges, services feed).

Projection honesty rules, learned from the ledger's own shape:
- **Income is never linearly extrapolated.** Paychecks are lumpy; on day 3 after one deposit a
  linear projection claims 10x income. Projected income = max(MTD, trailing median) — and the
  caller feeds a *3-month* median so a known income gap (the current parental leave) stops
  inflating the projection within a quarter.
- **Whole-month spend** blends linear extrapolation with the trailing median, weighted by month
  progress (w = elapsed/total): early in the month the median dominates (rent on the 1st would
  otherwise project 15x), late in the month actuals dominate.
- **Per-category pace** is linear (budgeted categories rarely have rent-shaped lumps) but returns
  no projection at all before MIN_ELAPSED_DAYS — a day-2 projection is noise, not signal.
- **A cut can never go below what's already spent** this month, or accepting it would manufacture
  an instant "over budget".
"""

import math
import uuid
from dataclasses import dataclass

MIN_ELAPSED_DAYS = 5  # before this, a linear projection is noise ("early")
DEFAULT_WATCH_FACTOR = 1.10  # projected within 10% over budget = "watch"; beyond = "over_pace"
DEFAULT_MAX_CUT_FRACTION = 0.5  # never propose cutting a category by more than half


@dataclass(frozen=True)
class CategoryPace:
    budget_cents: int
    spent_cents: int  # MTD magnitude (positive)
    projected_cents: int | None  # None while "early"
    remaining_cents: int  # budget - spent; may be negative
    daily_allowance_cents: int  # spend/day that lands exactly on budget; 0 when blown
    status: str  # "early" | "on_track" | "watch" | "over_pace" | "over"


def project_linear(mtd_cents: int, elapsed_days: int, total_days: int) -> int:
    """Straight-line month-end projection from month-to-date actuals."""
    elapsed = max(1, elapsed_days)
    return int(round(mtd_cents * (total_days / elapsed)))


def blend_projection(
    mtd_cents: int, trailing_median_cents: int, elapsed_days: int, total_days: int
) -> int:
    """Elapsed-weighted blend of linear extrapolation and the trailing median: the median anchors
    the projection early in the month, actuals take over as the month completes."""
    w = min(1.0, max(0.0, elapsed_days / max(1, total_days)))
    linear = project_linear(mtd_cents, elapsed_days, total_days)
    return int(round(w * linear + (1.0 - w) * trailing_median_cents))


def category_pace(
    budget_cents: int,
    spent_cents: int,
    elapsed_days: int,
    total_days: int,
    *,
    min_elapsed_days: int = MIN_ELAPSED_DAYS,
    watch_factor: float = DEFAULT_WATCH_FACTOR,
) -> CategoryPace:
    """Where one budgeted category stands right now.

    "over" (already blown) wins regardless of day; "early" suppresses the projection until enough
    of the month has elapsed for a linear pace to mean something; otherwise the projection sorts
    into on_track (<= budget), watch (<= watch_factor * budget), or over_pace.
    """
    remaining = budget_cents - spent_cents
    days_left = max(0, total_days - elapsed_days)
    daily_allowance = max(0, remaining) // max(1, days_left) if days_left > 0 else 0

    if spent_cents > budget_cents:
        projected: int | None = (
            project_linear(spent_cents, elapsed_days, total_days)
            if elapsed_days >= min_elapsed_days
            else None
        )
        status = "over"
    elif elapsed_days < min_elapsed_days:
        projected = None
        status = "early"
    else:
        projected = project_linear(spent_cents, elapsed_days, total_days)
        if projected <= budget_cents:
            status = "on_track"
        elif projected <= int(round(budget_cents * watch_factor)):
            status = "watch"
        else:
            status = "over_pace"

    return CategoryPace(
        budget_cents=budget_cents,
        spent_cents=spent_cents,
        projected_cents=projected,
        remaining_cents=remaining,
        daily_allowance_cents=daily_allowance,
        status=status,
    )


@dataclass(frozen=True)
class NetProjection:
    projected_income_cents: int
    projected_spend_cents: int
    projected_net_cents: int
    basis: str  # "blend" | "mtd_only" (no trailing history at all)


def project_net(
    *,
    mtd_income_cents: int,
    mtd_spend_cents: int,
    median_income_cents: int,
    median_spend_cents: int,
    elapsed_days: int,
    total_days: int,
) -> NetProjection:
    """Month-end net projection. Income = max(MTD, median) — never extrapolated (paychecks are
    lumpy and a known income gap should read low, not inflated). Spend = elapsed-weighted blend."""
    projected_income = max(mtd_income_cents, median_income_cents)
    projected_spend = blend_projection(
        mtd_spend_cents, median_spend_cents, elapsed_days, total_days
    )
    basis = "blend" if (median_income_cents > 0 or median_spend_cents > 0) else "mtd_only"
    return NetProjection(
        projected_income_cents=projected_income,
        projected_spend_cents=projected_spend,
        projected_net_cents=projected_income - projected_spend,
        basis=basis,
    )


@dataclass(frozen=True)
class CutCandidate:
    category_id: uuid.UUID
    category_name: str
    budget_id: uuid.UUID | None  # this month's budget row, if one exists
    baseline_cents: int  # current budget if set, else the trailing-median spend
    spent_cents: int  # MTD magnitude — the floor a cut can never go under
    fixed: bool  # bill-dominated category (rent, utilities): never proposed for cutting


@dataclass(frozen=True)
class ProposedCut:
    category_id: uuid.UUID
    category_name: str
    budget_id: uuid.UUID | None
    from_cents: int
    to_cents: int
    cut_cents: int


@dataclass(frozen=True)
class PlanResult:
    cuts: list[ProposedCut]
    achievable_cents: int
    shortfall_cents: int  # honest: how much of `needed` the plan could NOT reach


def plan_category_cuts(
    candidates: list[CutCandidate],
    needed_cents: int,
    *,
    max_cut_fraction: float = DEFAULT_MAX_CUT_FRACTION,
) -> PlanResult:
    """Greedy savings plan: cut the categories with the most headroom first until the target is
    met. Headroom per category = baseline minus its floor, where floor = max(already-spent MTD,
    baseline * (1 - max_cut_fraction)) — a cut never dips below money already spent and never
    slashes a category by more than max_cut_fraction. Fixed (bill-dominated) categories are
    untouchable. The last cut is trimmed to take only what's still needed."""
    if needed_cents <= 0:
        return PlanResult(cuts=[], achievable_cents=0, shortfall_cents=0)

    def floor_for(c: CutCandidate) -> int:
        return max(c.spent_cents, int(math.ceil(c.baseline_cents * (1.0 - max_cut_fraction))))

    eligible = [
        (c, c.baseline_cents - floor_for(c))
        for c in candidates
        if not c.fixed and c.baseline_cents - floor_for(c) > 0
    ]
    eligible.sort(key=lambda pair: -pair[1])

    cuts: list[ProposedCut] = []
    remaining = needed_cents
    for candidate, headroom in eligible:
        if remaining <= 0:
            break
        take = min(headroom, remaining)
        to_cents = candidate.baseline_cents - take
        cuts.append(
            ProposedCut(
                category_id=candidate.category_id,
                category_name=candidate.category_name,
                budget_id=candidate.budget_id,
                from_cents=candidate.baseline_cents,
                to_cents=to_cents,
                cut_cents=take,
            )
        )
        remaining -= take

    achievable = needed_cents - max(0, remaining)
    return PlanResult(cuts=cuts, achievable_cents=achievable, shortfall_cents=max(0, remaining))
