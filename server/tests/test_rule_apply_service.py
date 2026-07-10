"""Rules applied to history + AI drafts promoted to rules (ROADMAP Wave 3 #25).

This is the one place where an LLM suggestion becomes a persisted fact, so the guardrails get
the most attention: a rule must never overrule a human, a dry run must write nothing, and the
whole thing must be safe to run twice.
"""

import datetime
import uuid

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.account import Account
from app.models.category import Category
from app.models.rule import Rule
from app.models.transaction import Transaction
from app.models.user import User
from app.services.rule_apply_service import promote_suggestions_to_rules

DATE = datetime.date(2026, 7, 1)


def _email() -> str:
    return f"ruleapply-{uuid.uuid4().hex[:8]}@magpie.test"


async def _setup() -> tuple[uuid.UUID, uuid.UUID, dict[str, uuid.UUID]]:
    async with AsyncSessionLocal() as db:
        user = User(name="Rule Apply", email=_email())
        db.add(user)
        await db.flush()
        account = Account(user_id=user.id, name="Checking", institution="Test", type="depository")
        db.add(account)
        cats = {}
        for name in ("Groceries", "Dining"):
            c = Category(name=name, user_id=user.id)
            db.add(c)
            await db.flush()
            cats[name] = c.id
        await db.commit()
        return user.id, account.id, cats


async def _txn(account_id, merchant, amount=-1000, *, cat=None, draft=None, kind="spend"):
    async with AsyncSessionLocal() as db:
        t = Transaction(
            account_id=account_id,
            amount=amount,
            date=DATE,
            status="posted",
            kind=kind,
            source="csv",
            merchant_raw=merchant,
            merchant_norm=merchant,
            category_id=cat,
            ai_suggested_category_id=draft,
            review_state="needs_review",
        )
        db.add(t)
        await db.commit()
        return t.id


async def _get(txn_id) -> Transaction:
    async with AsyncSessionLocal() as db:
        return await db.get(Transaction, txn_id)


async def _rules(user_id) -> list[Rule]:
    async with AsyncSessionLocal() as db:
        return list((await db.execute(select(Rule).where(Rule.user_id == user_id))).scalars().all())


async def test_a_draft_becomes_a_rule_and_files_its_whole_history():
    user_id, account_id, cats = await _setup()
    ids = [await _txn(account_id, "THERESA", draft=cats["Groceries"]) for _ in range(3)]

    async with AsyncSessionLocal() as db:
        summary = await promote_suggestions_to_rules(db, user_id, dry_run=False)

    assert summary.rules_created == 1
    assert summary.transactions_filed == 3
    rules = await _rules(user_id)
    assert len(rules) == 1 and rules[0].matcher == "THERESA"
    assert rules[0].type == "merchant_category"

    for i in ids:
        t = await _get(i)
        assert t.category_id == cats["Groceries"]
        assert t.review_state == "auto"  # a rule hit is auto-filed, not queued
        assert t.matched_rule_id == rules[0].id
        assert t.rule_note == "matched rule: THERESA"


async def test_dry_run_reports_everything_and_writes_nothing():
    user_id, account_id, cats = await _setup()
    txn = await _txn(account_id, "THERESA", draft=cats["Groceries"])

    async with AsyncSessionLocal() as db:
        summary = await promote_suggestions_to_rules(db, user_id, dry_run=True)

    assert summary.dry_run is True
    assert summary.rules_created == 1 and summary.transactions_filed == 1
    assert await _rules(user_id) == []
    assert (await _get(txn)).category_id is None


async def test_a_rule_never_overrules_a_human_confirmed_category():
    """The law: a rule fills blanks. A row a person already categorized is left alone."""
    user_id, account_id, cats = await _setup()
    confirmed = await _txn(account_id, "THERESA", cat=cats["Dining"], draft=cats["Groceries"])
    blank = await _txn(account_id, "THERESA", draft=cats["Groceries"])

    async with AsyncSessionLocal() as db:
        await promote_suggestions_to_rules(db, user_id, dry_run=False, min_transactions=1)

    # The merchant has a confirmed row, so no rule is created for it at all...
    assert await _rules(user_id) == []
    assert (await _get(confirmed)).category_id == cats["Dining"]
    assert (await _get(blank)).category_id is None


async def test_running_twice_creates_one_rule_and_files_once():
    user_id, account_id, cats = await _setup()
    await _txn(account_id, "THERESA", draft=cats["Groceries"])

    async with AsyncSessionLocal() as db:
        first = await promote_suggestions_to_rules(db, user_id, dry_run=False)
    async with AsyncSessionLocal() as db:
        second = await promote_suggestions_to_rules(db, user_id, dry_run=False)

    assert first.rules_created == 1
    assert second.rules_created == 0  # the merchant already has a rule
    assert second.transactions_filed == 0
    assert len(await _rules(user_id)) == 1


async def test_a_merchant_whose_rows_disagree_on_the_draft_is_skipped():
    """Ambiguity is never resolved by guessing — it goes back to the human."""
    user_id, account_id, cats = await _setup()
    await _txn(account_id, "AMBIGUOUS", draft=cats["Groceries"])
    await _txn(account_id, "AMBIGUOUS", draft=cats["Dining"])

    async with AsyncSessionLocal() as db:
        summary = await promote_suggestions_to_rules(db, user_id, dry_run=False)

    assert summary.rules_created == 0
    assert summary.merchants_skipped == 2  # both (merchant, category) groups rejected
    assert await _rules(user_id) == []


async def test_min_transactions_holds_back_one_off_merchants():
    user_id, account_id, cats = await _setup()
    await _txn(account_id, "ONEOFF", draft=cats["Dining"])
    for _ in range(3):
        await _txn(account_id, "REGULAR", draft=cats["Groceries"])

    async with AsyncSessionLocal() as db:
        summary = await promote_suggestions_to_rules(db, user_id, dry_run=False, min_transactions=2)

    assert summary.rules_created == 1
    assert [r.matcher for r in await _rules(user_id)] == ["REGULAR"]


async def test_income_rows_are_not_categorized_by_a_merchant_rule():
    """Merchant→category rules are spend-side. Income direction is the transfer/recurring
    matchers' business, and a Zelle deposit must not inherit a spend category."""
    user_id, account_id, cats = await _setup()
    inc = await _txn(account_id, "THERESA", amount=5000, kind="income", draft=cats["Groceries"])
    await _txn(account_id, "THERESA", draft=cats["Groceries"])
    await _txn(account_id, "THERESA", draft=cats["Groceries"])

    async with AsyncSessionLocal() as db:
        summary = await promote_suggestions_to_rules(db, user_id, dry_run=False)

    assert summary.transactions_filed == 2
    assert (await _get(inc)).category_id is None


async def test_a_merchant_with_no_draft_gets_no_rule():
    user_id, account_id, _cats = await _setup()
    await _txn(account_id, "UNSEEN")

    async with AsyncSessionLocal() as db:
        summary = await promote_suggestions_to_rules(db, user_id, dry_run=False)

    assert summary.rules_created == 0
    assert await _rules(user_id) == []


# --- The endpoints -------------------------------------------------------------------------


async def _account_user(account_id: str) -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        return (await db.get(Account, uuid.UUID(account_id))).user_id


async def test_promote_endpoint_defaults_to_dry_run(auth_client):
    r = await auth_client.post(
        "/accounts", json={"name": "Checking", "institution": "T", "type": "depository"}
    )
    account_id = r.json()["id"]
    user_id = await _account_user(account_id)
    async with AsyncSessionLocal() as db:
        cat = Category(name="Groceries", user_id=user_id)
        db.add(cat)
        await db.commit()
        cat_id = cat.id
    await _txn(uuid.UUID(account_id), "THERESA", draft=cat_id)

    r = await auth_client.post("/rules/from-suggestions")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dry_run"] is True
    assert body["rules_created"] == 1
    assert body["applications"][0]["matcher"] == "THERESA"
    assert body["applications"][0]["category_name"] == "Groceries"

    assert (await auth_client.get("/rules")).json() == []  # nothing written


async def test_promote_endpoint_commits_when_asked(auth_client):
    r = await auth_client.post(
        "/accounts", json={"name": "Checking", "institution": "T", "type": "depository"}
    )
    account_id = r.json()["id"]
    user_id = await _account_user(account_id)
    async with AsyncSessionLocal() as db:
        cat = Category(name="Dining", user_id=user_id)
        db.add(cat)
        await db.commit()
        cat_id = cat.id
    await _txn(uuid.UUID(account_id), "CAFE", draft=cat_id)

    r = await auth_client.post("/rules/from-suggestions?dry_run=false")
    assert r.status_code == 200
    assert r.json()["transactions_filed"] == 1
    rules = (await auth_client.get("/rules")).json()
    assert len(rules) == 1 and rules[0]["matcher"] == "CAFE"


async def test_promote_endpoint_requires_auth(client):
    assert (await client.post("/rules/from-suggestions")).status_code == 401
