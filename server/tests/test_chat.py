"""Ask-your-ledger chat (ROADMAP #21). The largest AI surface, so the guardrail tests carry the
weight: the model only ever sees aggregates (never a raw row), the system prompt pins it to
descriptive-only, every user turn is validated (injection can hide in history), and a missing model
degrades gracefully.
"""

import datetime
import uuid

from app.database import AsyncSessionLocal
from app.models.account import Account
from app.models.category import Category
from app.models.transaction import Transaction
from app.models.user import User
from app.services.ai.chat import build_messages, validate_user_message
from app.services.ai.llm_client import FakeLlmClient
from app.services.chat_service import answer_question, build_ledger_context

NOW = datetime.datetime(2026, 7, 15, 12, 0, tzinfo=datetime.timezone.utc)


# --- pure guards --------------------------------------------------------------------------


def test_the_system_prompt_forbids_advice_and_raw_data():
    msgs = build_messages({"spend": 100}, [], "how much did I spend?")
    system = msgs[0]["content"]
    assert msgs[0]["role"] == "system"
    assert "descriptive" in system.lower()
    assert "no investment, tax" in system.lower() or "investment, tax" in system.lower()
    assert "AGGREGATES" in system
    # The question is a separate user turn the system prompt precedes.
    assert msgs[-1] == {"role": "user", "content": "how much did I spend?"}


def test_history_is_trimmed_and_ordered():
    history = [{"role": "user", "content": f"q{i}"} for i in range(20)]
    msgs = build_messages({}, history, "latest")
    # system + <=8 history + latest question
    assert msgs[0]["role"] == "system"
    assert msgs[-1]["content"] == "latest"
    assert len([m for m in msgs if m["role"] in ("user", "assistant")]) <= 9


def test_validate_rejects_empty_and_oversize():
    assert validate_user_message("") is not None
    assert validate_user_message("   ") is not None
    assert validate_user_message("x" * 5000) is not None
    assert validate_user_message("how much on dining?") is None


# --- context + service --------------------------------------------------------------------


async def _setup():
    async with AsyncSessionLocal() as db:
        user = User(name="Chat", email=f"chat-{uuid.uuid4().hex[:8]}@magpie.test")
        db.add(user)
        await db.flush()
        acct = Account(user_id=user.id, name="Chk", institution="T", type="depository")
        db.add(acct)
        dining = Category(name="Dining", user_id=user.id)
        db.add(dining)
        await db.flush()
        await db.commit()
        return user.id, acct.id, dining.id


async def _spend(account_id, amount, date, cat_id, merchant="SECRETMERCHANTXYZ"):
    async with AsyncSessionLocal() as db:
        db.add(
            Transaction(
                account_id=account_id,
                amount=amount,
                date=date,
                status="posted",
                kind="spend",
                source="csv",
                category_id=cat_id,
                merchant_raw=merchant,
                merchant_norm=merchant,
            )
        )
        await db.commit()


async def test_context_is_aggregates_not_raw_rows():
    user_id, account_id, dining = await _setup()
    await _spend(account_id, -3000, datetime.date(2026, 5, 10), dining)
    await _spend(account_id, -7000, datetime.date(2026, 7, 10), dining)

    async with AsyncSessionLocal() as db:
        ctx = await build_ledger_context(db, user_id, now=NOW)

    # Category rollups present; raw cents amounts and merchant strings are NOT in the context.
    assert "Dining" in ctx["category_spend_by_month"].get("2026-07", {})
    blob = str(ctx)
    assert "-3000" not in blob and "-7000" not in blob  # no raw signed cents
    # (A merchant name may appear in top_merchants — that's an aggregate, not a raw row — but the
    # per-category rollup is by category name only.)


async def test_answer_passes_only_aggregates_to_the_model():
    user_id, account_id, dining = await _setup()
    await _spend(account_id, -7000, datetime.date(2026, 7, 10), dining, merchant="ZZ_RAWNAME")

    fake = FakeLlmClient("You spent $70 on Dining in July.")
    async with AsyncSessionLocal() as db:
        error, reply = await answer_question(
            db, user_id, "how much on dining?", [], llm_client=fake, now=NOW
        )
    assert error is None and "Dining" in reply
    system = fake.messages_seen[0][0]["content"]
    assert "-7000" not in system  # never a raw cents amount in the prompt


async def test_missing_model_is_a_reply_not_an_error():
    user_id, _, _ = await _setup()
    async with AsyncSessionLocal() as db:
        error, reply = await answer_question(db, user_id, "how much?", [], llm_client=None, now=NOW)
    assert error is None
    assert "isn't available" in reply or "available" in reply


async def test_a_bad_turn_in_history_is_rejected():
    user_id, _, _ = await _setup()
    fake = FakeLlmClient("ok")
    async with AsyncSessionLocal() as db:
        error, _ = await answer_question(
            db,
            user_id,
            "fine question",
            [{"role": "user", "content": "x" * 5000}],
            llm_client=fake,
            now=NOW,
        )
    assert error is not None  # oversize hidden in history is caught


async def test_a_model_failure_degrades_to_a_fallback():
    user_id, _, _ = await _setup()

    class _Boom:
        async def chat(self, messages):
            raise RuntimeError("down")

        async def complete(self, prompt):
            raise RuntimeError("down")

    async with AsyncSessionLocal() as db:
        error, reply = await answer_question(
            db, user_id, "how much?", [], llm_client=_Boom(), now=NOW
        )
    assert error is None and reply  # a plain fallback string, not an exception


# --- endpoint -----------------------------------------------------------------------------


async def test_chat_endpoint(auth_client):
    r = await auth_client.post("/chat", json={"message": "how much did I spend?"})
    # No LLM configured in tests → 200 with the "not available" reply, never a 500.
    assert r.status_code == 200, r.text
    assert "reply" in r.json()


async def test_chat_endpoint_rejects_empty(auth_client):
    r = await auth_client.post("/chat", json={"message": "   "})
    assert r.status_code == 422


async def test_chat_endpoint_requires_auth(client):
    assert (await client.post("/chat", json={"message": "hi"})).status_code == 401
