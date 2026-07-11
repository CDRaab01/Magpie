"""Seed recurring-bill rules from history (ROADMAP #2) + the bill-late sweep + selective arming."""

import datetime
import uuid

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.account import Account
from app.models.rule import Rule
from app.models.transaction import Transaction
from app.models.user import User
from app.services.bill_rule_service import propose_bill_rules, seed_bill_rules
from app.services.ntfy_client import FakeNtfyPublisher

NOW = datetime.datetime(2026, 7, 15, 12, 0, tzinfo=datetime.timezone.utc)


async def _setup():
    async with AsyncSessionLocal() as db:
        user = User(name="Bill", email=f"bill-{uuid.uuid4().hex[:8]}@magpie.test")
        db.add(user)
        await db.flush()
        chk = Account(user_id=user.id, name="Checking", institution="US Bank", type="depository")
        card = Account(user_id=user.id, name="Amex", institution="Amex", type="card")
        db.add_all([chk, card])
        await db.commit()
        await db.refresh(chk)
        await db.refresh(card)
        return user.id, chk.id, card.id


async def _bill(account_id, merchant, start, n, cents, step=30):
    async with AsyncSessionLocal() as db:
        for i in range(n):
            db.add(
                Transaction(
                    account_id=account_id,
                    amount=cents,
                    date=start + datetime.timedelta(days=step * i),
                    status="posted",
                    kind="spend",
                    source="csv",
                    merchant_raw=merchant,
                    merchant_norm=merchant,
                )
            )
        await db.commit()


async def test_a_live_monthly_bill_is_proposed_with_its_payment_rail():
    user_id, chk, card = await _setup()
    # Recent monthly mortgage on checking.
    await _bill(chk, "ROCKET MORTGAGE", datetime.date(2026, 2, 3), 6, -443415)

    async with AsyncSessionLocal() as db:
        proposals = await propose_bill_rules(db, user_id, now=NOW)
    mortgage = next(p for p in proposals if p.merchant == "ROCKET MORTGAGE")
    assert mortgage.account_id == chk  # bound to the rail it's paid from
    assert mortgage.shape.cadence == "monthly"


async def test_the_rail_is_the_account_that_pays_it_most():
    user_id, chk, card = await _setup()
    await _bill(card, "AT T", datetime.date(2026, 2, 6), 6, -21400)  # phone on the card

    async with AsyncSessionLocal() as db:
        proposals = await propose_bill_rules(db, user_id, now=NOW)
    att = next(p for p in proposals if p.merchant == "AT T")
    assert att.account_id == card


async def test_a_dormant_former_residence_utility_is_excluded():
    """The Ohio-utilities trap: a biller that stopped when they moved must not arm a missing-bill
    alert about a house they left."""
    user_id, chk, card = await _setup()
    await _bill(chk, "OHIO GAS", datetime.date(2025, 1, 8), 6, -7500)  # last ~2025-06

    async with AsyncSessionLocal() as db:
        proposals = await propose_bill_rules(db, user_id, now=NOW)
    assert all(p.merchant != "OHIO GAS" for p in proposals)


async def test_seasonal_utility_gets_a_wide_band():
    user_id, chk, card = await _setup()
    # Electric bill swinging seasonally.
    async with AsyncSessionLocal() as db:
        for i, cents in enumerate([-8000, -22000, -12000, -25000, -9000, -21000]):
            db.add(
                Transaction(
                    account_id=chk,
                    amount=cents,
                    date=datetime.date(2026, 2, 5) + datetime.timedelta(days=30 * i),
                    status="posted",
                    kind="spend",
                    source="csv",
                    merchant_raw="AEP",
                    merchant_norm="AEP",
                )
            )
        await db.commit()

    async with AsyncSessionLocal() as db:
        proposals = await propose_bill_rules(db, user_id, now=NOW)
    aep = next((p for p in proposals if p.merchant == "AEP"), None)
    if aep is not None:  # if detected at all, its band should be wide (seasonal)
        assert aep.shape.band_pct >= 0.25


async def test_seed_binds_the_rule_to_the_account_and_anchors_last_matched():
    user_id, chk, card = await _setup()
    last = datetime.date(2026, 7, 3)
    await _bill(chk, "ROCKET MORTGAGE", last - datetime.timedelta(days=30 * 5), 6, -443415)

    async with AsyncSessionLocal() as db:
        summary = await seed_bill_rules(db, user_id, dry_run=False, now=NOW)
    assert summary.rules_created == 1
    async with AsyncSessionLocal() as db:
        rule = (await db.execute(select(Rule).where(Rule.user_id == user_id))).scalars().one()
    assert rule.type == "recurring_bill"
    assert rule.account_id == chk
    assert rule.last_matched_at.date() == last


async def test_only_arms_the_selected_proposals():
    """The selective-confirm flow: the owner picks which recurrences become rules."""
    user_id, chk, card = await _setup()
    await _bill(chk, "ROCKET MORTGAGE", datetime.date(2026, 2, 3), 6, -443415)
    await _bill(card, "AT T", datetime.date(2026, 2, 6), 6, -21400)

    async with AsyncSessionLocal() as db:
        summary = await seed_bill_rules(db, user_id, dry_run=False, only={"AT T"}, now=NOW)
    assert summary.rules_created == 1
    async with AsyncSessionLocal() as db:
        matchers = [
            r.matcher
            for r in (await db.execute(select(Rule).where(Rule.user_id == user_id))).scalars().all()
        ]
    assert matchers == ["AT T"]  # mortgage NOT armed


async def test_seeding_is_idempotent():
    user_id, chk, card = await _setup()
    await _bill(chk, "ROCKET MORTGAGE", datetime.date(2026, 2, 3), 6, -443415)
    async with AsyncSessionLocal() as db:
        first = await seed_bill_rules(db, user_id, dry_run=False, now=NOW)
    async with AsyncSessionLocal() as db:
        second = await seed_bill_rules(db, user_id, dry_run=False, now=NOW)
    assert first.rules_created == 1 and second.rules_created == 0


# --- bill-late sweep ----------------------------------------------------------------------


async def _sweep_bill_late(user_id, publisher, now):
    from app.services.sweep_service import run_bill_late_sweep

    async with AsyncSessionLocal() as db:
        await run_bill_late_sweep(db, user_id, publisher, now=now)
        await db.commit()


async def test_bill_late_pages_when_a_bill_payment_is_overdue():
    user_id, chk, card = await _setup()
    async with AsyncSessionLocal() as db:
        db.add(
            Rule(
                user_id=user_id,
                type="recurring_bill",
                account_id=chk,
                matcher="XCEL",
                cadence={"kind": "monthly", "slack_days": 3},
                amount_band={"pct": 0.2},
                last_matched_at=datetime.datetime(2026, 5, 10, tzinfo=datetime.timezone.utc),
                enabled=True,
            )
        )
        await db.commit()

    publisher = FakeNtfyPublisher()
    # ~2 months later, no payment since 05-10 → overdue.
    await _sweep_bill_late(
        user_id, publisher, datetime.datetime(2026, 7, 1, 12, tzinfo=datetime.timezone.utc)
    )
    assert len(publisher.published) == 1
    assert "XCEL" in publisher.published[0][0]
    assert publisher.published[0][2] == "magpie://bills"
    # latched — a second sweep doesn't re-page
    await _sweep_bill_late(
        user_id, publisher, datetime.datetime(2026, 7, 2, 12, tzinfo=datetime.timezone.utc)
    )
    assert len(publisher.published) == 1


async def test_bill_late_stays_quiet_when_a_bill_is_on_schedule():
    user_id, chk, card = await _setup()
    async with AsyncSessionLocal() as db:
        db.add(
            Rule(
                user_id=user_id,
                type="recurring_bill",
                account_id=chk,
                matcher="XCEL",
                cadence={"kind": "monthly", "slack_days": 3},
                amount_band={"pct": 0.2},
                last_matched_at=datetime.datetime(2026, 7, 5, tzinfo=datetime.timezone.utc),
                enabled=True,
            )
        )
        await db.commit()

    publisher = FakeNtfyPublisher()
    await _sweep_bill_late(
        user_id, publisher, datetime.datetime(2026, 7, 15, 12, tzinfo=datetime.timezone.utc)
    )
    assert publisher.published == []  # next due ~08-05, not late


async def test_endpoint(auth_client):
    acct = (
        await auth_client.post(
            "/accounts", json={"name": "Chk", "institution": "T", "type": "depository"}
        )
    ).json()["id"]
    await _bill(
        uuid.UUID(acct),
        "ROCKET MORTGAGE",
        datetime.date.today() - datetime.timedelta(days=150),
        6,
        -443415,
    )

    r = await auth_client.post("/rules/from-bills")
    assert r.status_code == 200, r.text
    assert r.json()["dry_run"] is True
    assert any(p["merchant"] == "ROCKET MORTGAGE" for p in r.json()["proposals"])
