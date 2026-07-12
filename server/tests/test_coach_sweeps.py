"""Coach sweeps (Stage 2): budget-pace nudge (batched, latched per category+month) and the
savings-goal risk page. Time-travel via pinned `now`, FakeNtfyPublisher, same seams as the
other sweep tests."""

import datetime
import uuid

from app.database import AsyncSessionLocal
from app.models.account import Account
from app.models.budget import Budget
from app.models.category import Category
from app.models.goal import Goal
from app.models.transaction import Transaction
from app.models.user import User
from app.services.ntfy_client import FakeNtfyPublisher
from app.services.sweep_service import run_budget_pace_sweep, run_savings_goal_sweep

UTC = datetime.timezone.utc
# Mid-July 2026: owner-local day 15 of 31 — past the min-day guard, projections meaningful.
MID_MONTH = datetime.datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
EARLY_MONTH = datetime.datetime(2026, 7, 5, 12, 0, tzinfo=UTC)
THIS_MONTH = datetime.date(2026, 7, 1)


async def _user_account():
    async with AsyncSessionLocal() as db:
        user = User(name="Coach", email=f"coach-{uuid.uuid4().hex[:8]}@magpie.test")
        db.add(user)
        await db.flush()
        acct = Account(user_id=user.id, name="Checking", institution="T", type="depository")
        db.add(acct)
        await db.commit()
        return user.id, acct.id


async def _budgeted_spend(user_id, account_id, name, budget_cents, spent_cents):
    """A category with a budget this month and MTD spend."""
    async with AsyncSessionLocal() as db:
        cat = Category(user_id=user_id, name=name)
        db.add(cat)
        await db.flush()
        db.add(Budget(user_id=user_id, category_id=cat.id, month=THIS_MONTH, amount=budget_cents))
        if spent_cents:
            db.add(
                Transaction(
                    account_id=account_id,
                    amount=-spent_cents,
                    date=datetime.date(2026, 7, 10),
                    status="posted",
                    kind="spend",
                    source="csv",
                    merchant_raw=name.upper(),
                    merchant_norm=name.upper(),
                    category_id=cat.id,
                )
            )
        await db.commit()
        return cat.id


async def _sweep_pace(user_id, publisher, now):
    async with AsyncSessionLocal() as db:
        await run_budget_pace_sweep(db, user_id, publisher, now=now)
        await db.commit()


async def _sweep_goal(user_id, publisher, now):
    async with AsyncSessionLocal() as db:
        await run_savings_goal_sweep(db, user_id, publisher, now=now)
        await db.commit()


# --- budget pace ----------------------------------------------------------------------------


async def test_pace_holds_fire_before_min_day_then_pages_once():
    user_id, acct = await _user_account()
    # $140 of $150 by day 10 -> projects way over.
    await _budgeted_spend(user_id, acct, "Dining", 15000, 14000)

    publisher = FakeNtfyPublisher()
    await _sweep_pace(user_id, publisher, EARLY_MONTH)
    assert publisher.published == []  # day 5: guard holds

    await _sweep_pace(user_id, publisher, MID_MONTH)
    assert len(publisher.published) == 1  # day 15: pages
    body, title, click = publisher.published[0]
    assert "Dining" in body and "on pace for" in body
    assert click == "magpie://budgets"

    await _sweep_pace(user_id, publisher, MID_MONTH)
    assert len(publisher.published) == 1  # latched: no re-page


async def test_pace_batches_multiple_offenders_into_one_message():
    user_id, acct = await _user_account()
    await _budgeted_spend(user_id, acct, "Dining", 15000, 14000)
    await _budgeted_spend(user_id, acct, "Fun", 20000, 19000)

    publisher = FakeNtfyPublisher()
    await _sweep_pace(user_id, publisher, MID_MONTH)
    assert len(publisher.published) == 1  # ONE message, not two
    body, title, _ = publisher.published[0]
    assert "2 budgets over pace" in body
    assert "Dining" in body and "Fun" in body


async def test_pace_floor_suppresses_tiny_budgets_and_on_track_stays_quiet():
    user_id, acct = await _user_account()
    await _budgeted_spend(user_id, acct, "Vending", 2000, 1900)  # wild pace, $19 spent < floor
    await _budgeted_spend(user_id, acct, "Groceries", 60000, 20000)  # on track

    publisher = FakeNtfyPublisher()
    await _sweep_pace(user_id, publisher, MID_MONTH)
    assert publisher.published == []


async def test_pace_already_blown_budget_pages():
    user_id, acct = await _user_account()
    await _budgeted_spend(user_id, acct, "Dining", 10000, 12000)  # over on day 15

    publisher = FakeNtfyPublisher()
    await _sweep_pace(user_id, publisher, MID_MONTH)
    assert len(publisher.published) == 1


async def test_pace_later_offender_still_pages_after_first_batch():
    user_id, acct = await _user_account()
    await _budgeted_spend(user_id, acct, "Dining", 15000, 14000)
    publisher = FakeNtfyPublisher()
    await _sweep_pace(user_id, publisher, MID_MONTH)
    assert len(publisher.published) == 1

    # A second category goes over later in the month — its own latch, fresh page.
    await _budgeted_spend(user_id, acct, "Fun", 20000, 19000)
    await _sweep_pace(user_id, publisher, datetime.datetime(2026, 7, 20, 12, 0, tzinfo=UTC))
    assert len(publisher.published) == 2
    assert "Fun" in publisher.published[1][0]
    assert "Dining" not in publisher.published[1][0]  # still latched, not re-included


# --- savings goal ---------------------------------------------------------------------------


async def _goal(user_id, cents):
    async with AsyncSessionLocal() as db:
        db.add(Goal(user_id=user_id, kind="monthly_savings", amount_cents=cents, active=True))
        await db.commit()


async def _month_of_history(user_id, acct, month_date, income_cents, spend_cents):
    async with AsyncSessionLocal() as db:
        cat = Category(user_id=user_id, name=f"H{month_date:%m}{uuid.uuid4().hex[:4]}")
        db.add(cat)
        await db.flush()
        db.add(
            Transaction(
                account_id=acct,
                amount=income_cents,
                date=month_date,
                status="posted",
                kind="income",
                source="csv",
                merchant_raw="JOB",
                merchant_norm="JOB",
            )
        )
        db.add(
            Transaction(
                account_id=acct,
                amount=-spend_cents,
                date=month_date,
                status="posted",
                kind="spend",
                source="csv",
                merchant_raw="LIFE",
                merchant_norm="LIFE",
                category_id=cat.id,
            )
        )
        await db.commit()


async def _july_mtd_spend(user_id, acct, cents):
    """July spend before day 15 so the blend projection reflects a month actually in motion."""
    async with AsyncSessionLocal() as db:
        cat = Category(user_id=user_id, name=f"MTD{uuid.uuid4().hex[:4]}")
        db.add(cat)
        await db.flush()
        db.add(
            Transaction(
                account_id=acct,
                amount=-cents,
                date=datetime.date(2026, 7, 10),
                status="posted",
                kind="spend",
                source="csv",
                merchant_raw="LIFE",
                merchant_norm="LIFE",
                category_id=cat.id,
            )
        )
        await db.commit()


async def test_goal_sweep_noop_without_goal_and_pages_when_projected_short():
    user_id, acct = await _user_account()
    # 3 prior months: $1000 income, $900 spend; July already at $450 by day 15 (on its usual
    # pace) -> projected net lands near $85-$100, far short of a $500 goal.
    for m in (4, 5, 6):
        await _month_of_history(user_id, acct, datetime.date(2026, m, 15), 100000, 90000)
    await _july_mtd_spend(user_id, acct, 45000)

    publisher = FakeNtfyPublisher()
    await _sweep_goal(user_id, publisher, MID_MONTH)
    assert publisher.published == []  # no goal -> silence

    await _goal(user_id, 50000)  # $500 goal vs ~$85 projected net
    await _sweep_goal(user_id, publisher, MID_MONTH)
    assert len(publisher.published) == 1
    body, title, click = publisher.published[0]
    assert "savings goal" in body and click == "magpie://budgets"

    await _sweep_goal(user_id, publisher, MID_MONTH)
    assert len(publisher.published) == 1  # latched for the month


async def test_goal_sweep_within_slack_stays_quiet():
    user_id, acct = await _user_account()
    for m in (4, 5, 6):
        await _month_of_history(user_id, acct, datetime.date(2026, m, 15), 100000, 90000)
    await _july_mtd_spend(user_id, acct, 45000)
    # Projected net ~ $85-$100; a goal ~$10 above it is inside the $25 slack -> quiet.
    await _goal(user_id, 10500)

    publisher = FakeNtfyPublisher()
    await _sweep_goal(user_id, publisher, MID_MONTH)
    assert publisher.published == []


async def test_goal_sweep_respects_min_day():
    user_id, acct = await _user_account()
    for m in (4, 5, 6):
        await _month_of_history(user_id, acct, datetime.date(2026, m, 15), 100000, 90000)
    await _goal(user_id, 500000)

    publisher = FakeNtfyPublisher()
    await _sweep_goal(user_id, publisher, EARLY_MONTH)
    assert publisher.published == []


# --- Link A: the cooking lever in the pace nudge ------------------------------------------


async def test_dining_over_pace_carries_the_cooking_fact(monkeypatch):
    from app.services import cross_app_client
    from app.services.cross_app_client import CookedWindow

    user_id, acct = await _user_account()
    await _budgeted_spend(user_id, acct, "Dining out", 15000, 14000)

    async def fake_window(email, *, now, client=None):
        return CookedWindow(last_14_days=2, prior_14_days=8)

    monkeypatch.setattr(cross_app_client, "fetch_cooked_window", fake_window)
    publisher = FakeNtfyPublisher()
    await _sweep_pace(user_id, publisher, MID_MONTH)
    body = publisher.published[0][0]
    assert "2 home-cooked meal(s) in the last 14 days" in body
    assert "cooking is the lever" in body


async def test_non_dining_over_pace_has_no_cooking_fact(monkeypatch):
    from app.services import cross_app_client
    from app.services.cross_app_client import CookedWindow

    user_id, acct = await _user_account()
    await _budgeted_spend(user_id, acct, "Hobbies", 15000, 14000)

    called = {"n": 0}

    async def fake_window(email, *, now, client=None):
        called["n"] += 1
        return CookedWindow(last_14_days=2, prior_14_days=8)

    monkeypatch.setattr(cross_app_client, "fetch_cooked_window", fake_window)
    publisher = FakeNtfyPublisher()
    await _sweep_pace(user_id, publisher, MID_MONTH)
    assert "cooking" not in publisher.published[0][0]
    assert called["n"] == 0  # rule 7: no "read everything just in case"


async def test_cookbook_silent_means_no_cooking_line(monkeypatch):
    from app.services import cross_app_client

    user_id, acct = await _user_account()
    await _budgeted_spend(user_id, acct, "Dining out", 15000, 14000)

    async def fake_window(email, *, now, client=None):
        return None  # Cookbook didn't say

    monkeypatch.setattr(cross_app_client, "fetch_cooked_window", fake_window)
    publisher = FakeNtfyPublisher()
    await _sweep_pace(user_id, publisher, MID_MONTH)
    body = publisher.published[0][0]
    assert "cooking" not in body and "Cookbook" not in body
