"""Seed recurring-income rules from history (ROADMAP #1). The two guards are the point — a former
employer must not become a live "late paycheck" alert (recency), and a $8 interest credit is not a
paycheck (floor) — because both are traps the real ledger contains (VERANEX stopped 2025-05;
MONTHLY MAINTENANCE FEE WAIVED recurs at $8).
"""

import datetime
import uuid

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.account import Account
from app.models.rule import Rule
from app.models.transaction import Transaction
from app.models.user import User
from app.rules.income import detect_income
from app.services.income_rule_service import propose_income_rules, seed_income_rules

NOW = datetime.datetime(2026, 7, 15, 12, 0, tzinfo=datetime.timezone.utc)


def _biweekly(start: datetime.date, n: int, cents: int, jitter=0):
    return [
        (start + datetime.timedelta(days=14 * i), cents + (jitter if i % 2 else -jitter))
        for i in range(n)
    ]


# --- pure detection -----------------------------------------------------------------------


def test_a_steady_biweekly_paycheck_is_detected():
    shape = detect_income(_biweekly(datetime.date(2026, 1, 2), 8, 500000))
    assert shape is not None
    assert shape.cadence == "biweekly"
    assert shape.typical_amount_cents == 500000
    assert 0.15 <= shape.band_pct <= 0.40


def test_a_variable_paycheck_gets_a_wider_band_than_a_steady_one():
    steady = detect_income(_biweekly(datetime.date(2026, 1, 2), 8, 500000, jitter=5000))
    variable = detect_income(_biweekly(datetime.date(2026, 1, 2), 8, 500000, jitter=90000))
    assert variable.band_pct > steady.band_pct


def test_chaotic_amounts_are_not_income():
    # Person-to-person: same cadence, wildly different amounts.
    chaotic = [
        (datetime.date(2026, 1, 2) + datetime.timedelta(days=14 * i), amt)
        for i, amt in enumerate([5000, 135000, 25000, 90000, 5000, 200000])
    ]
    assert detect_income(chaotic) is None


def test_too_few_deposits_is_not_income():
    assert detect_income(_biweekly(datetime.date(2026, 6, 1), 3, 500000)) is None


# --- service guards -----------------------------------------------------------------------


async def _user_account():
    async with AsyncSessionLocal() as db:
        user = User(name="Income", email=f"inc-{uuid.uuid4().hex[:8]}@magpie.test")
        db.add(user)
        await db.flush()
        acct = Account(user_id=user.id, name="Chk", institution="T", type="depository")
        db.add(acct)
        await db.commit()
        return user.id, acct.id


async def _deposits(account_id, merchant, start, n, cents, step=14):
    async with AsyncSessionLocal() as db:
        for i in range(n):
            db.add(
                Transaction(
                    account_id=account_id,
                    amount=cents,
                    date=start + datetime.timedelta(days=step * i),
                    status="posted",
                    kind="income",
                    source="csv",
                    merchant_raw=merchant,
                    merchant_norm=merchant,
                )
            )
        await db.commit()


async def test_a_current_paycheck_is_proposed():
    user_id, account_id = await _user_account()
    # Biweekly, ending a week before "now" — live.
    await _deposits(account_id, "EMPLOYER", datetime.date(2026, 4, 10), 7, 500000)

    async with AsyncSessionLocal() as db:
        proposals = await propose_income_rules(db, user_id, now=NOW)
    assert any(p.merchant == "EMPLOYER" for p in proposals)


async def test_a_former_employer_is_excluded_by_the_recency_gate():
    """The VERANEX trap: a stream that stopped over a year ago must NOT be armed, or paycheck-late
    would immediately page about a paycheck that ended long ago."""
    user_id, account_id = await _user_account()
    await _deposits(account_id, "OLDJOB", datetime.date(2024, 6, 1), 8, 450000)  # last ~2024-08

    async with AsyncSessionLocal() as db:
        proposals = await propose_income_rules(db, user_id, now=NOW)
    assert all(p.merchant != "OLDJOB" for p in proposals)


async def test_small_recurring_credits_are_excluded_by_the_floor():
    """The interest/fee-waiver trap: recurring by cadence, but $8 is not a paycheck."""
    user_id, account_id = await _user_account()
    await _deposits(account_id, "INTEREST PAID", datetime.date(2026, 4, 1), 6, 800, step=30)

    async with AsyncSessionLocal() as db:
        proposals = await propose_income_rules(db, user_id, now=NOW)
    assert all(p.merchant != "INTEREST PAID" for p in proposals)


async def test_seeding_anchors_last_matched_to_the_latest_deposit():
    """The arming safeguard: last_matched_at is the newest deposit, so paycheck-late's next-date
    math starts from reality rather than pinging about a paycheck that already came."""
    user_id, account_id = await _user_account()
    last = datetime.date(2026, 7, 8)
    await _deposits(account_id, "EMPLOYER", last - datetime.timedelta(days=14 * 6), 7, 500000)

    async with AsyncSessionLocal() as db:
        summary = await seed_income_rules(db, user_id, dry_run=False, now=NOW)

    assert summary.rules_created == 1
    async with AsyncSessionLocal() as db:
        rule = (await db.execute(select(Rule).where(Rule.user_id == user_id))).scalars().one()
    assert rule.type == "recurring_income"
    assert rule.last_matched_at.date() == last
    assert rule.cadence["kind"] == "biweekly"
    assert rule.amount_band["pct"] >= 0.15


async def test_seeding_is_idempotent():
    user_id, account_id = await _user_account()
    await _deposits(account_id, "EMPLOYER", datetime.date(2026, 4, 10), 7, 500000)

    async with AsyncSessionLocal() as db:
        first = await seed_income_rules(db, user_id, dry_run=False, now=NOW)
    async with AsyncSessionLocal() as db:
        second = await seed_income_rules(db, user_id, dry_run=False, now=NOW)
    assert first.rules_created == 1 and second.rules_created == 0


async def test_dry_run_writes_nothing():
    user_id, account_id = await _user_account()
    await _deposits(account_id, "EMPLOYER", datetime.date(2026, 4, 10), 7, 500000)

    async with AsyncSessionLocal() as db:
        summary = await seed_income_rules(db, user_id, dry_run=True, now=NOW)
    assert summary.rules_created == 1
    async with AsyncSessionLocal() as db:
        assert (
            await db.execute(select(Rule).where(Rule.user_id == user_id))
        ).scalars().first() is None


async def test_endpoint(auth_client):
    r = await auth_client.post(
        "/accounts", json={"name": "Chk", "institution": "T", "type": "depository"}
    )
    account_id = r.json()["id"]
    await _deposits(
        uuid.UUID(account_id),
        "EMPLOYER",
        datetime.date.today() - datetime.timedelta(days=90),
        7,
        500000,
    )

    r = await auth_client.post("/rules/from-income")
    assert r.status_code == 200, r.text
    assert r.json()["dry_run"] is True
    assert any(p["merchant"] == "EMPLOYER" for p in r.json()["proposals"])
