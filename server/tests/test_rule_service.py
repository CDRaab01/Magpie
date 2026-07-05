import datetime
import uuid

from app.database import AsyncSessionLocal
from app.models.account import Account
from app.models.rule import Rule
from app.models.transaction import Transaction
from app.models.user import User
from app.services.rule_service import MIN_OBSERVATIONS_TO_AUTOFILE, evaluate_transaction

NOW = datetime.datetime(2026, 7, 5, tzinfo=datetime.timezone.utc)


def _unique_email() -> str:
    return f"rule-test-{uuid.uuid4().hex[:8]}@magpie.test"


async def _make_user() -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        user = User(name="Rule Test", email=_unique_email())
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user.id


async def _make_account(user_id: uuid.UUID, name: str, type_: str) -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        account = Account(user_id=user_id, name=name, institution="Test Bank", type=type_)
        db.add(account)
        await db.commit()
        await db.refresh(account)
        return account.id


async def test_no_rules_and_no_transfer_falls_through_to_needs_review():
    user_id = await _make_user()
    account_id = await _make_account(user_id, "Checking", "depository")

    async with AsyncSessionLocal() as db:
        result = await evaluate_transaction(
            db,
            user_id,
            account_id=account_id,
            amount_cents=-500,
            txn_date=datetime.date(2026, 7, 1),
            merchant_raw="Coffee Shop",
            default_kind="spend",
            now=NOW,
        )
    assert result.kind == "spend"
    assert result.review_state == "needs_review"
    assert result.matched_rule_id is None


async def test_transfer_pair_auto_files_both_sides():
    user_id = await _make_user()
    checking_id = await _make_account(user_id, "Checking", "depository")
    card_id = await _make_account(user_id, "Amex", "card")

    # An existing, unmatched card-side inflow (the payment credit) already sitting in the DB.
    async with AsyncSessionLocal() as db:
        partner = Transaction(
            account_id=card_id,
            amount=5000,
            date=datetime.date(2026, 7, 4),
            status="posted",
            kind="income",
            review_state="needs_review",
            source="csv",
        )
        db.add(partner)
        await db.commit()
        await db.refresh(partner)

    async with AsyncSessionLocal() as db:
        result = await evaluate_transaction(
            db,
            user_id,
            account_id=checking_id,
            amount_cents=-5000,
            txn_date=datetime.date(2026, 7, 5),
            merchant_raw=None,
            default_kind="spend",
            now=NOW,
        )
        await db.commit()

    assert result.kind == "transfer"
    assert result.review_state == "auto"
    assert result.transfer_group is not None

    async with AsyncSessionLocal() as db:
        refreshed = await db.get(Transaction, partner.id)
        assert refreshed.kind == "transfer"
        assert refreshed.review_state == "auto"
        assert refreshed.transfer_group == result.transfer_group


async def test_recurring_rule_below_observation_threshold_stays_needs_review():
    user_id = await _make_user()
    account_id = await _make_account(user_id, "Checking", "depository")

    async with AsyncSessionLocal() as db:
        rule = Rule(
            user_id=user_id,
            type="recurring_bill",
            account_id=account_id,
            matcher="XCEL ENERGY",
            cadence={"kind": "monthly", "slack_days": 5},
            amount_band={"pct": 0.2},
        )
        db.add(rule)
        await db.commit()
        await db.refresh(rule)

    async with AsyncSessionLocal() as db:
        result = await evaluate_transaction(
            db,
            user_id,
            account_id=account_id,
            amount_cents=-3500,
            txn_date=datetime.date(2026, 7, 15),
            merchant_raw="XCEL ENERGY 88213091",
            default_kind="spend",
            now=NOW,
        )

    assert result.review_state == "needs_review"
    assert result.matched_rule_id == rule.id
    assert f"0/{MIN_OBSERVATIONS_TO_AUTOFILE}" in result.rule_note


async def test_recurring_rule_autofiles_once_observations_and_band_and_cadence_hold():
    user_id = await _make_user()
    account_id = await _make_account(user_id, "Checking", "depository")

    async with AsyncSessionLocal() as db:
        rule = Rule(
            user_id=user_id,
            type="recurring_bill",
            account_id=account_id,
            matcher="XCEL ENERGY",
            cadence={"kind": "monthly", "slack_days": 5},
            amount_band={"pct": 0.2},
            last_matched_at=datetime.datetime(2026, 6, 15, tzinfo=datetime.timezone.utc),
        )
        db.add(rule)
        await db.commit()
        await db.refresh(rule)

        # Three prior observations (the "backfill history" CLAUDE.md's cold-start bar counts).
        for month, amount in ((4, -3000), (5, -3200), (6, -3400)):
            db.add(
                Transaction(
                    account_id=account_id,
                    amount=amount,
                    date=datetime.date(2026, month, 15),
                    status="posted",
                    merchant_raw="XCEL ENERGY",
                    merchant_norm="XCEL ENERGY",
                    kind="spend",
                    review_state="auto",
                    source="csv",
                )
            )
        await db.commit()

    async with AsyncSessionLocal() as db:
        result = await evaluate_transaction(
            db,
            user_id,
            account_id=account_id,
            amount_cents=-3300,
            txn_date=datetime.date(2026, 7, 16),
            merchant_raw="XCEL ENERGY 99001122",
            default_kind="spend",
            now=NOW,
        )

    assert result.kind == "spend"
    assert result.review_state == "auto"
    assert result.matched_rule_id == rule.id
    assert "Matched rule: XCEL ENERGY" in result.rule_note


async def test_recurring_rule_out_of_band_amount_stays_needs_review():
    user_id = await _make_user()
    account_id = await _make_account(user_id, "Checking", "depository")

    async with AsyncSessionLocal() as db:
        rule = Rule(
            user_id=user_id,
            type="recurring_bill",
            account_id=account_id,
            matcher="XCEL ENERGY",
            cadence={"kind": "monthly", "slack_days": 5},
            amount_band={"pct": 0.2},
            last_matched_at=datetime.datetime(2026, 6, 15, tzinfo=datetime.timezone.utc),
        )
        db.add(rule)
        await db.commit()

        for month, amount in ((4, -3000), (5, -3200), (6, -3400)):
            db.add(
                Transaction(
                    account_id=account_id,
                    amount=amount,
                    date=datetime.date(2026, month, 15),
                    status="posted",
                    merchant_raw="XCEL ENERGY",
                    merchant_norm="XCEL ENERGY",
                    kind="spend",
                    review_state="auto",
                    source="csv",
                )
            )
        await db.commit()

    async with AsyncSessionLocal() as db:
        # $90 is wildly outside a ~$30-34 median band.
        result = await evaluate_transaction(
            db,
            user_id,
            account_id=account_id,
            amount_cents=-9000,
            txn_date=datetime.date(2026, 7, 16),
            merchant_raw="XCEL ENERGY 12345678",
            default_kind="spend",
            now=NOW,
        )

    assert result.review_state == "needs_review"
    assert "out of band" in result.rule_note


async def test_merchant_category_rule_autofiles_with_category():
    user_id = await _make_user()
    account_id = await _make_account(user_id, "Amex", "card")

    async with AsyncSessionLocal() as db:
        rule = Rule(
            user_id=user_id,
            type="merchant_category",
            account_id=account_id,
            matcher="NETFLIX",
        )
        db.add(rule)
        await db.commit()
        await db.refresh(rule)

    async with AsyncSessionLocal() as db:
        result = await evaluate_transaction(
            db,
            user_id,
            account_id=account_id,
            amount_cents=-1599,
            txn_date=datetime.date(2026, 7, 1),
            merchant_raw="NETFLIX.COM",
            default_kind="spend",
            now=NOW,
        )

    assert result.review_state == "auto"
    assert result.matched_rule_id == rule.id
