import datetime
import uuid

from app.database import AsyncSessionLocal
from app.models.account import Account
from app.models.category import Category
from app.models.rule import Rule
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.transaction import TransactionUpdate
from app.services.ai.llm_client import FakeLlmClient
from app.services.rule_service import MIN_OBSERVATIONS_TO_AUTOFILE, evaluate_transaction
from app.services.transaction_service import update_transaction

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


async def test_f3_confirmed_partner_is_not_silently_rewritten_into_a_transfer():
    # A human-confirmed card payment already sits in the ledger. A new checking outflow that
    # would otherwise pair with it must NOT flip the confirmed row to "auto"/"transfer" — the
    # new row routes to review instead, and the confirmed partner is left exactly as it was.
    user_id = await _make_user()
    checking_id = await _make_account(user_id, "Checking", "depository")
    card_id = await _make_account(user_id, "Amex", "card")

    async with AsyncSessionLocal() as db:
        partner = Transaction(
            account_id=card_id,
            amount=5000,
            date=datetime.date(2026, 7, 4),
            status="posted",
            kind="income",
            review_state="confirmed",  # the human already reviewed this one
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

    assert result.kind == "spend"
    assert result.review_state == "needs_review"
    assert result.transfer_group is None

    async with AsyncSessionLocal() as db:
        refreshed = await db.get(Transaction, partner.id)
        assert refreshed.kind == "income"  # untouched
        assert refreshed.review_state == "confirmed"
        assert refreshed.transfer_group is None


async def test_f3_card_spend_and_coincidental_deposit_do_not_pair_end_to_end():
    # The F3 false positive through the real evaluator: a card spend and a same-amount checking
    # deposit must not fuse. The candidate (a card spend, negative on the card) finds no
    # payment-shaped partner in the deposit.
    user_id = await _make_user()
    checking_id = await _make_account(user_id, "Checking", "depository")
    card_id = await _make_account(user_id, "Amex", "card")

    async with AsyncSessionLocal() as db:
        deposit = Transaction(
            account_id=checking_id,
            amount=5000,
            date=datetime.date(2026, 7, 4),
            status="posted",
            kind="income",
            review_state="needs_review",
            source="csv",
        )
        db.add(deposit)
        await db.commit()

    async with AsyncSessionLocal() as db:
        result = await evaluate_transaction(
            db,
            user_id,
            account_id=card_id,
            amount_cents=-5000,  # a card spend, not a payment
            txn_date=datetime.date(2026, 7, 5),
            merchant_raw="Coffee Shop",
            default_kind="spend",
            now=NOW,
        )
        await db.commit()

    assert result.kind == "spend"
    assert result.transfer_group is None


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


async def test_no_rule_match_with_llm_configured_drafts_never_confirms():
    user_id = await _make_user()
    account_id = await _make_account(user_id, "Amex", "card")

    async with AsyncSessionLocal() as db:
        category = Category(user_id=user_id, name="Dining")
        db.add(category)
        await db.commit()
        await db.refresh(category)

    client = FakeLlmClient('{"category_name": "Dining", "reasoning": "restaurant"}')
    async with AsyncSessionLocal() as db:
        result = await evaluate_transaction(
            db,
            user_id,
            account_id=account_id,
            amount_cents=-3200,
            txn_date=datetime.date(2026, 7, 1),
            merchant_raw="SAMPLE BISTRO",
            default_kind="spend",
            now=NOW,
            llm_client=client,
        )

    # The draft lands in ai_suggested_category_id ONLY — category_id and review_state are
    # untouched by the model (CLAUDE.md §6: nothing it produces is persisted as confirmed).
    assert result.ai_suggested_category_id == category.id
    assert result.category_id is None
    assert result.review_state == "needs_review"


async def test_no_llm_client_configured_never_calls_the_model():
    user_id = await _make_user()
    account_id = await _make_account(user_id, "Amex", "card")

    async with AsyncSessionLocal() as db:
        result = await evaluate_transaction(
            db,
            user_id,
            account_id=account_id,
            amount_cents=-3200,
            txn_date=datetime.date(2026, 7, 1),
            merchant_raw="SAMPLE BISTRO",
            default_kind="spend",
            now=NOW,
        )

    assert result.ai_suggested_category_id is None
    assert result.review_state == "needs_review"


# --- F6: rules survive a miss --------------------------------------------------------------


async def _seed_observations(account_id: uuid.UUID, merchant_norm: str, dates):
    async with AsyncSessionLocal() as db:
        for d in dates:
            db.add(
                Transaction(
                    account_id=account_id,
                    amount=-8000,
                    date=d,
                    status="posted",
                    kind="spend",
                    review_state="confirmed",
                    source="csv",
                    merchant_raw=merchant_norm,
                    merchant_norm=merchant_norm,
                )
            )
        await db.commit()


async def test_f6_autofile_anchors_rule_window_to_transaction_date_not_now():
    # A delayed/backfill row (dated in May) auto-files in July's run — the rule's window must
    # anchor to the transaction's date, not wall-clock `now`, or every future occurrence desyncs.
    user_id = await _make_user()
    account_id = await _make_account(user_id, "Checking", "depository")
    await _seed_observations(
        account_id,
        "XCEL",
        [datetime.date(2026, 2, 15), datetime.date(2026, 3, 15), datetime.date(2026, 4, 15)],
    )
    async with AsyncSessionLocal() as db:
        rule = Rule(
            user_id=user_id,
            type="recurring_bill",
            account_id=account_id,
            matcher="XCEL",
            cadence={"kind": "monthly", "slack_days": 5},
        )
        db.add(rule)
        await db.commit()
        await db.refresh(rule)
        rule_id = rule.id

    async with AsyncSessionLocal() as db:
        result = await evaluate_transaction(
            db,
            user_id,
            account_id=account_id,
            amount_cents=-8000,
            txn_date=datetime.date(2026, 5, 15),
            merchant_raw="XCEL ENERGY",
            default_kind="spend",
            now=NOW,  # 2026-07-05 — deliberately far from the transaction date
        )
        await db.commit()

    assert result.review_state == "auto"
    async with AsyncSessionLocal() as db:
        refreshed = await db.get(Rule, rule_id)
        assert refreshed.last_matched_at.date() == datetime.date(2026, 5, 15)


async def test_f6_confirming_a_flagged_transaction_advances_its_rule():
    # The core F6 bug: a miss routes to review, the human confirms, but the rule never advances
    # so it reads "outside cadence window" forever. Confirming must move the window forward.
    user_id = await _make_user()
    account_id = await _make_account(user_id, "Checking", "depository")
    async with AsyncSessionLocal() as db:
        rule = Rule(
            user_id=user_id,
            type="recurring_bill",
            account_id=account_id,
            matcher="XCEL",
            cadence={"kind": "monthly", "slack_days": 5},
            last_matched_at=datetime.datetime(2026, 5, 15, tzinfo=datetime.timezone.utc),
        )
        db.add(rule)
        await db.commit()
        await db.refresh(rule)
        rule_id = rule.id
        txn = Transaction(
            account_id=account_id,
            amount=-8000,
            date=datetime.date(2026, 7, 25),  # out of the monthly window ⇒ was flagged for review
            status="posted",
            kind="spend",
            review_state="needs_review",
            source="csv",
            merchant_raw="XCEL ENERGY",
            merchant_norm="XCEL",
            matched_rule_id=rule_id,
        )
        db.add(txn)
        await db.commit()
        await db.refresh(txn)
        txn_id = txn.id

    async with AsyncSessionLocal() as db:
        await update_transaction(db, user_id, txn_id, TransactionUpdate(review_state="confirmed"))

    async with AsyncSessionLocal() as db:
        refreshed = await db.get(Rule, rule_id)
        assert refreshed.last_matched_at.date() == datetime.date(2026, 7, 25)


async def test_f6_confirm_never_moves_the_rule_window_backward():
    # A late-confirmed OLDER row must not drag the window back and re-open the desync.
    user_id = await _make_user()
    account_id = await _make_account(user_id, "Checking", "depository")
    async with AsyncSessionLocal() as db:
        rule = Rule(
            user_id=user_id,
            type="recurring_bill",
            account_id=account_id,
            matcher="XCEL",
            cadence={"kind": "monthly", "slack_days": 5},
            last_matched_at=datetime.datetime(2026, 7, 25, tzinfo=datetime.timezone.utc),
        )
        db.add(rule)
        await db.commit()
        await db.refresh(rule)
        rule_id = rule.id
        txn = Transaction(
            account_id=account_id,
            amount=-8000,
            date=datetime.date(2026, 6, 1),  # older than the current window anchor
            status="posted",
            kind="spend",
            review_state="needs_review",
            source="csv",
            merchant_raw="XCEL ENERGY",
            merchant_norm="XCEL",
            matched_rule_id=rule_id,
        )
        db.add(txn)
        await db.commit()
        await db.refresh(txn)
        txn_id = txn.id

    async with AsyncSessionLocal() as db:
        await update_transaction(db, user_id, txn_id, TransactionUpdate(review_state="confirmed"))

    async with AsyncSessionLocal() as db:
        refreshed = await db.get(Rule, rule_id)
        assert refreshed.last_matched_at.date() == datetime.date(2026, 7, 25)
