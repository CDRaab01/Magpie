"""Muting a merchant as 'not a subscription' (ROADMAP #12) — drops it from the screen and both
subscription sweeps."""

import datetime
import uuid

from app.database import AsyncSessionLocal
from app.models.account import Account
from app.models.subscription_mute import SubscriptionMute
from app.models.transaction import Transaction
from app.models.user import User
from app.services.ntfy_client import FakeNtfyPublisher
from app.services.subscription_service import list_subscriptions

NOW = datetime.datetime(2026, 7, 15, 12, 0, tzinfo=datetime.timezone.utc)


async def _user_account():
    async with AsyncSessionLocal() as db:
        user = User(name="Mute", email=f"mute-{uuid.uuid4().hex[:8]}@magpie.test")
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
                    account_id=account_id, amount=cents,
                    date=start + datetime.timedelta(days=30 * i),
                    status="posted", kind="spend", source="csv",
                    merchant_raw=merchant, merchant_norm=merchant,
                )
            )
        await db.commit()


async def _mute(user_id, merchant):
    async with AsyncSessionLocal() as db:
        db.add(SubscriptionMute(user_id=user_id, merchant=merchant))
        await db.commit()


async def test_a_muted_merchant_drops_off_the_list():
    user_id, account_id = await _user_account()
    await _charges(account_id, "SHELL GAS", datetime.date(2026, 2, 1), 6, -4000)
    await _charges(account_id, "NETFLIX", datetime.date(2026, 2, 1), 6, -1599)
    await _mute(user_id, "SHELL GAS")

    async with AsyncSessionLocal() as db:
        subs = await list_subscriptions(db, user_id, now=NOW)
    assert [s.merchant for s in subs] == ["NETFLIX"]  # gas muted, netflix stays


async def test_a_muted_merchant_does_not_fire_the_new_recurrence_sweep():
    from app.services.sweep_service import run_subscription_sweeps

    user_id, account_id = await _user_account()
    await _charges(account_id, "SHELL GAS", datetime.date(2026, 2, 1), 6, -4000)
    await _mute(user_id, "SHELL GAS")

    publisher = FakeNtfyPublisher()
    async with AsyncSessionLocal() as db:
        await run_subscription_sweeps(db, user_id, publisher, now=NOW)
        await db.commit()
    assert publisher.published == []  # muted -> no "new subscription" page


async def test_mute_endpoint_is_idempotent_and_unmute_restores(auth_client):
    acct = (await auth_client.post(
        "/accounts", json={"name": "Card", "institution": "T", "type": "card"})).json()["id"]
    # A subscription-shaped merchant so it shows up.
    async with AsyncSessionLocal() as db:
        for i in range(6):
            db.add(Transaction(
                account_id=uuid.UUID(acct), amount=-1599,
                date=datetime.date(2026, 2, 1) + datetime.timedelta(days=30 * i),
                status="posted", kind="spend", source="csv",
                merchant_raw="NETFLIX", merchant_norm="NETFLIX",
            ))
        await db.commit()

    assert any(s["merchant"] == "NETFLIX"
               for s in (await auth_client.get("/subscriptions")).json()["subscriptions"])

    # Mute twice — idempotent (204 both times), listed once.
    assert (await auth_client.post("/subscriptions/mute", json={"merchant": "NETFLIX"})).status_code == 204
    assert (await auth_client.post("/subscriptions/mute", json={"merchant": "NETFLIX"})).status_code == 204
    assert (await auth_client.get("/subscriptions/mutes")).json() == ["NETFLIX"]
    assert (await auth_client.get("/subscriptions")).json()["subscriptions"] == []

    # Unmute restores it.
    assert (await auth_client.request(
        "DELETE", "/subscriptions/mute", json={"merchant": "NETFLIX"})).status_code == 204
    assert (await auth_client.get("/subscriptions/mutes")).json() == []
    assert any(s["merchant"] == "NETFLIX"
               for s in (await auth_client.get("/subscriptions")).json()["subscriptions"])
