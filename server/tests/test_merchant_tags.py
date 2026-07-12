"""Merchant tags → Spotter cost-per-visit on the subscriptions screen (federated awareness Link G).

Tagging a gym membership "fitness" makes Magpie fetch this month's training-day count from Spotter
and show the subscription's cost-per-visit. Best-effort: Spotter quiet ⇒ the row is unchanged."""

import datetime
import uuid

from app.database import AsyncSessionLocal
from app.models.transaction import Transaction
from app.services import cross_app_client
from app.services.subscription_service import cost_per_visit_cents


def test_cost_per_visit_splits_monthly_cost():
    # $600/yr = $50/mo; 10 visits ⇒ $5.00/visit.
    assert cost_per_visit_cents(60000, 10) == 500


def test_cost_per_visit_none_at_zero_visits():
    assert cost_per_visit_cents(60000, 0) is None


async def _seed_gym(auth_client) -> str:
    """A subscription-shaped GYM charge on the authed user's account; returns the account id."""
    acct = (
        await auth_client.post(
            "/accounts", json={"name": "Card", "institution": "T", "type": "card"}
        )
    ).json()["id"]
    async with AsyncSessionLocal() as db:
        for i in range(6):
            db.add(
                Transaction(
                    account_id=uuid.UUID(acct),
                    amount=-5000,  # $50/mo
                    date=datetime.date(2026, 2, 1) + datetime.timedelta(days=30 * i),
                    status="posted",
                    kind="spend",
                    source="csv",
                    merchant_raw="CITY GYM",
                    merchant_norm="CITY GYM",
                )
            )
        await db.commit()
    return acct


def _gym(body) -> dict:
    return next(s for s in body["subscriptions"] if s["merchant"] == "CITY GYM")


async def test_tag_endpoint_idempotent_and_untag(auth_client):
    await _seed_gym(auth_client)
    # Untagged: no tags, no decoration.
    assert _gym((await auth_client.get("/subscriptions")).json())["tags"] == []

    # Tag twice — idempotent (204 both), listed once.
    assert (
        await auth_client.post(
            "/subscriptions/tag", json={"merchant": "CITY GYM", "tag": "fitness"}
        )
    ).status_code == 204
    assert (
        await auth_client.post(
            "/subscriptions/tag", json={"merchant": "CITY GYM", "tag": "fitness"}
        )
    ).status_code == 204
    assert _gym((await auth_client.get("/subscriptions")).json())["tags"] == ["fitness"]

    # Untag restores the bare row.
    assert (
        await auth_client.request(
            "DELETE", "/subscriptions/tag", json={"merchant": "CITY GYM", "tag": "fitness"}
        )
    ).status_code == 204
    assert _gym((await auth_client.get("/subscriptions")).json())["tags"] == []


async def test_unknown_tag_is_rejected(auth_client):
    resp = await auth_client.post(
        "/subscriptions/tag", json={"merchant": "CITY GYM", "tag": "bogus"}
    )
    assert resp.status_code == 422


async def test_fitness_tag_shows_visits_and_cost_per_visit(auth_client, monkeypatch):
    await _seed_gym(auth_client)
    await auth_client.post("/subscriptions/tag", json={"merchant": "CITY GYM", "tag": "fitness"})

    async def fake_visits(email, *, now, client=None):
        return 12

    monkeypatch.setattr(cross_app_client, "fetch_month_workout_visits", fake_visits)

    gym = _gym((await auth_client.get("/subscriptions")).json())
    assert gym["visits_this_month"] == 12
    # cost-per-visit = (annual/12)/12, computed off the row's own annual cost to stay robust.
    assert gym["cost_per_visit_cents"] == cost_per_visit_cents(gym["annual_cost_cents"], 12)


async def test_zero_visits_shows_count_but_no_cost(auth_client, monkeypatch):
    await _seed_gym(auth_client)
    await auth_client.post("/subscriptions/tag", json={"merchant": "CITY GYM", "tag": "fitness"})

    async def fake_visits(email, *, now, client=None):
        return 0

    monkeypatch.setattr(cross_app_client, "fetch_month_workout_visits", fake_visits)

    gym = _gym((await auth_client.get("/subscriptions")).json())
    assert gym["visits_this_month"] == 0  # paying, not going — the story is the 0
    assert gym["cost_per_visit_cents"] is None


async def test_spotter_absent_leaves_row_bare(auth_client, monkeypatch):
    await _seed_gym(auth_client)
    await auth_client.post("/subscriptions/tag", json={"merchant": "CITY GYM", "tag": "fitness"})

    async def fake_visits(email, *, now, client=None):
        return None  # Spotter didn't answer — absence, not zero

    monkeypatch.setattr(cross_app_client, "fetch_month_workout_visits", fake_visits)

    gym = _gym((await auth_client.get("/subscriptions")).json())
    assert gym["tags"] == ["fitness"]
    assert gym["visits_this_month"] is None
    assert gym["cost_per_visit_cents"] is None


async def test_untagged_merchant_never_calls_spotter(auth_client, monkeypatch):
    await _seed_gym(auth_client)

    called = {"n": 0}

    async def fake_visits(email, *, now, client=None):
        called["n"] += 1
        return 12

    monkeypatch.setattr(cross_app_client, "fetch_month_workout_visits", fake_visits)

    gym = _gym((await auth_client.get("/subscriptions")).json())
    assert gym["visits_this_month"] is None
    assert called["n"] == 0  # nothing tagged ⇒ no cross-app call at all
