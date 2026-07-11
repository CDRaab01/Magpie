"""Pure budget-pace + savings-plan math (AI budget coach, app/rules/pace.py)."""

import uuid

from app.rules.pace import (
    CutCandidate,
    blend_projection,
    category_pace,
    plan_category_cuts,
    project_linear,
    project_net,
)

# --- projections ----------------------------------------------------------------------------


def test_linear_projection_scales_mtd_to_month_end():
    assert project_linear(10000, 10, 30) == 30000


def test_blend_is_median_dominated_early_and_actuals_dominated_late():
    # Day 2 of 30: rent posted on the 1st would linearly project 15x — the median anchors it.
    early = blend_projection(150000, 200000, 2, 30)
    assert early < 400000  # nowhere near the 2.25M linear explosion
    # Day 28 of 30: actuals dominate.
    late = blend_projection(150000, 999999, 28, 30)
    assert abs(late - project_linear(150000, 28, 30)) < 100000


def test_income_is_never_extrapolated():
    # Day 3 after one $2k paycheck: linear would claim $20k income. max(mtd, median) doesn't.
    net = project_net(
        mtd_income_cents=200000,
        mtd_spend_cents=50000,
        median_income_cents=400000,
        median_spend_cents=300000,
        elapsed_days=3,
        total_days=30,
    )
    assert net.projected_income_cents == 400000  # the median, not 10x the paycheck


def test_income_floor_uses_mtd_when_it_already_beat_the_median():
    net = project_net(
        mtd_income_cents=500000,
        mtd_spend_cents=0,
        median_income_cents=400000,
        median_spend_cents=0,
        elapsed_days=20,
        total_days=30,
    )
    assert net.projected_income_cents == 500000
    assert net.basis == "blend"


def test_no_history_at_all_is_mtd_only():
    net = project_net(
        mtd_income_cents=100,
        mtd_spend_cents=100,
        median_income_cents=0,
        median_spend_cents=0,
        elapsed_days=15,
        total_days=30,
    )
    assert net.basis == "mtd_only"


# --- category pace --------------------------------------------------------------------------


def test_early_month_has_no_projection():
    pace = category_pace(15000, 14000, 2, 30)  # wild pace on day 2 — still "early"
    assert pace.status == "early"
    assert pace.projected_cents is None


def test_status_boundaries():
    # Projected exactly at budget -> on_track. spent=5000 over 10 of 30 days -> projects 15000.
    assert category_pace(15000, 5000, 10, 30).status == "on_track"
    # Projects 10% over exactly -> watch (boundary inclusive).
    assert category_pace(15000, 5500, 10, 30).status == "watch"  # projects 16500 == 1.10*15000
    # Beyond the watch band -> over_pace.
    assert category_pace(15000, 6000, 10, 30).status == "over_pace"  # projects 18000


def test_already_blown_budget_is_over_regardless_of_day():
    pace = category_pace(10000, 12000, 1, 31)
    assert pace.status == "over"
    assert pace.remaining_cents == -2000
    assert pace.daily_allowance_cents == 0


def test_daily_allowance_is_what_keeps_it_on_budget():
    pace = category_pace(15000, 10000, 18, 30)  # $50 left, 12 days
    assert pace.daily_allowance_cents == 5000 // 12


# --- savings planner ------------------------------------------------------------------------


def _cand(name, baseline, spent=0, fixed=False, budget_id=None):
    return CutCandidate(
        category_id=uuid.uuid4(),
        category_name=name,
        budget_id=budget_id,
        baseline_cents=baseline,
        spent_cents=spent,
        fixed=fixed,
    )


def test_planner_cuts_largest_headroom_first_and_trims_the_last_cut():
    plan = plan_category_cuts([_cand("Dining", 30000), _cand("Fun", 10000)], 20000)
    assert [c.category_name for c in plan.cuts] == ["Dining", "Fun"]
    assert plan.cuts[0].cut_cents == 15000  # capped at 50% of 30000
    assert plan.cuts[1].cut_cents == 5000  # trimmed: only what's still needed
    assert plan.achievable_cents == 20000 and plan.shortfall_cents == 0


def test_cut_never_goes_below_what_is_already_spent():
    # $120 already spent against a $150 baseline: max cut is $30, not $75.
    plan = plan_category_cuts([_cand("Dining", 15000, spent=12000)], 10000)
    assert plan.cuts[0].to_cents == 12000
    assert plan.cuts[0].cut_cents == 3000
    assert plan.shortfall_cents == 7000  # honest about the miss


def test_fixed_categories_are_untouchable():
    plan = plan_category_cuts([_cand("Housing", 400000, fixed=True), _cand("Dining", 20000)], 50000)
    assert all(c.category_name != "Housing" for c in plan.cuts)
    assert plan.shortfall_cents == 40000  # only Dining's 10k headroom was available


def test_already_on_target_needs_no_cuts():
    plan = plan_category_cuts([_cand("Dining", 30000)], 0)
    assert plan.cuts == [] and plan.achievable_cents == 0 and plan.shortfall_cents == 0
