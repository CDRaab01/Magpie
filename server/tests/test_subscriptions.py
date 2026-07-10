"""Subscription surfacing (ROADMAP #22): recurrence detection, the /subscriptions read model,
and the new-recurrence + price-hike sweeps."""

import datetime
import uuid

from app.database import AsyncSessionLocal
from app.models.account import Account
from app.models.rule import Rule
from app.models.transaction import Transaction
from app.models.user import User
from app.rules.subscriptions import detect_recurrence, price_hike_cents
from app.services.ntfy_client import FakeNtfyPublisher
from app.services.subscription_service import list_subscriptions

NOW = datetime.datetime(2026, 7, 15, 12, 0, tzinfo=datetime.timezone.utc)


def _monthly(start: datetime.date, n: int, cents: int) -> list[tuple[datetime.date, int]]:
    return [(start + datetime.timedelta(days=30 * i), cents) for i in range(n)]


# --- pure detection -----------------------------------------------------------------------


def test_a_steady_monthly_charge_is_a_subscription():
    rec = detect_recurrence(_monthly(datetime.date(2026, 1, 5), 5, -1599))
    assert rec is not None
    assert rec.cadence == "monthly"
    assert rec.typical_amount_cents == 1599
    assert rec.annual_cost_cents == 1599 * 12


def test_too_few_occurrences_is_not_a_subscription():
    assert detect_recurrence(_monthly(datetime.date(2026, 1, 5), 2, -1599)) is None


def test_irregular_intervals_are_not_a_subscription():
    dated = [
        (datetime.date(2026, 1, 1), -1000),
        (datetime.date(2026, 1, 3), -1000),
        (datetime.date(2026, 5, 20), -1000),
    ]
    assert detect_recurrence(dated) is None


def test_wildly_varying_amounts_are_not_a_subscription():
    dated = [
        (datetime.date(2026, 1, 5), -500),
        (datetime.date(2026, 2, 5), -9000),
        (datetime.date(2026, 3, 5), -300),
    ]
    assert detect_recurrence(dated) is None


def test_price_hike_detected_only_when_latest_breaks_upward():
    steady = detect_recurrence(_monthly(datetime.date(2026, 1, 5), 5, -1000))
    assert price_hike_cents(steady) is None
    # Same history but the last charge jumps to $15.
    hiked = detect_recurrence(
        _monthly(datetime.date(2026, 1, 5), 4, -1000) + [(datetime.date(2026, 6, 5), -1500)]
    )
    assert hiked is not None
    assert price_hike_cents(hiked) == 500


# --- read model + sweeps ------------------------------------------------------------------


async def _user_account():
    async with AsyncSessionLocal() as db:
        user = User(name="Sub", email=f"sub-{uuid.uuid4().hex[:8]}@magpie.test")
        db.add(user)
        await db.flush()
        acct = Account(user_id=user.id, name="Card", institution="T", type="card")
        db.add(acct)
        await db.commit()
        return user.id, acct.id


async def _charges(account_id, merchant, start, n, cents):
    async with AsyncSessionLocal() as db:
        for i in range(n):
            db.add(
                Transaction(
                    account_id=account_id,
                    amount=cents,
                    date=start + datetime.timedelta(days=30 * i),
                    status="posted",
                    kind="spend",
                    source="csv",
                    merchant_raw=merchant,
                    merchant_norm=merchant,
                )
            )
        await db.commit()


async def test_list_subscriptions_sorted_by_annual_cost():
    user_id, account_id = await _user_account()
    await _charges(account_id, "NETFLIX", datetime.date(2026, 2, 1), 5, -1599)
    await _charges(account_id, "GYM", datetime.date(2026, 2, 1), 5, -5000)

    async with AsyncSessionLocal() as db:
        subs = await list_subscriptions(db, user_id, now=NOW)

    assert [s.merchant for s in subs] == ["GYM", "NETFLIX"]  # gym costs more per year


async def _sweep(user_id, publisher, now=NOW):
    from app.services.sweep_service import run_subscription_sweeps

    async with AsyncSessionLocal() as db:
        await run_subscription_sweeps(db, user_id, publisher, now=now)
        await db.commit()


async def test_new_recurrence_pages_once_then_latches():
    user_id, account_id = await _user_account()
    await _charges(account_id, "SPOTIFY", datetime.date(2026, 3, 1), 4, -1099)

    publisher = FakeNtfyPublisher()
    await _sweep(user_id, publisher)
    assert any("SPOTIFY" in m for m, _t, _c in publisher.published)
    n = len(publisher.published)
    await _sweep(user_id, publisher)  # latched
    assert len(publisher.published) == n


async def test_a_merchant_that_already_has_a_rule_is_not_a_new_recurrence():
    user_id, account_id = await _user_account()
    await _charges(account_id, "HULU", datetime.date(2026, 3, 1), 4, -1299)
    async with AsyncSessionLocal() as db:
        db.add(Rule(user_id=user_id, type="merchant_category", matcher="HULU", enabled=True))
        await db.commit()

    publisher = FakeNtfyPublisher()
    await _sweep(user_id, publisher)
    assert not any("new subscription" in t.lower() for _m, t, _c in publisher.published)


async def test_price_hike_pages():
    user_id, account_id = await _user_account()
    await _charges(account_id, "NETFLIX", datetime.date(2026, 2, 1), 4, -1599)
    # Fifth charge jumps.
    async with AsyncSessionLocal() as db:
        db.add(
            Transaction(
                account_id=account_id,
                amount=-1899,
                date=datetime.date(2026, 6, 1),
                status="posted",
                kind="spend",
                source="csv",
                merchant_raw="NETFLIX",
                merchant_norm="NETFLIX",
            )
        )
        await db.commit()

    publisher = FakeNtfyPublisher()
    await _sweep(user_id, publisher)
    assert any("went up" in m for m, _t, _c in publisher.published)


async def test_subscriptions_endpoint(auth_client):
    r = await auth_client.post(
        "/accounts", json={"name": "Card", "institution": "T", "type": "card"}
    )
    account_id = r.json()["id"]
    await _charges(uuid.UUID(account_id), "ADOBE", datetime.date(2026, 2, 1), 5, -2099)

    r = await auth_client.get("/subscriptions")
    assert r.status_code == 200, r.text
    body = r.json()
    assert any(
        s["merchant"] == "ADOBE" and s["cadence"] == "monthly" for s in body["subscriptions"]
    )
    assert body["total_annual_cost_cents"] >= 2099 * 12


# --- alert narration (#19) ----------------------------------------------------------------


async def test_narrate_deviation_appends_a_line():
    from app.services.ai.llm_client import FakeLlmClient
    from app.services.ai.narrate import narrate_deviation

    line = await narrate_deviation(
        FakeLlmClient("The last time it ran this high was March."), "facts"
    )
    assert line == "The last time it ran this high was March."


async def test_narrate_deviation_is_best_effort_on_failure():
    from app.services.ai.narrate import narrate_deviation

    class _Boom:
        async def complete(self, prompt):
            raise RuntimeError("model down")

    assert await narrate_deviation(_Boom(), "facts") is None


async def test_narrate_deviation_truncates_a_runaway_reply():
    from app.services.ai.llm_client import FakeLlmClient
    from app.services.ai.narrate import narrate_deviation

    line = await narrate_deviation(FakeLlmClient("x" * 500), "facts")
    assert line is not None and len(line) <= 140
