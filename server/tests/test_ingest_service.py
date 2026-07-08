"""Mock-the-seam E2E (CLAUDE.md §9, the Hawksnest `mock-ha` precedent): real `.eml` fixtures,
parsed by the real parsers, fed through the real service and a real (throwaway) DB — only the
IMAP socket itself is faked.
"""

import email
import uuid
from email.utils import parsedate_to_datetime
from pathlib import Path

from app.database import AsyncSessionLocal
from app.ingest.imap_client import FakeImapFetcher, FetchedEmail, _plaintext_body
from app.models.account import Account
from app.models.ingest_event import IngestEvent
from app.models.transaction import Transaction
from app.models.user import User
from app.services.ingest_service import run_ingest_poll

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_eml(name: str) -> FetchedEmail:
    """Loads a fixture with a freshly minted Message-ID on every call. The fixture files carry
    a fixed placeholder id; reusing that id verbatim across different test functions collides
    against whatever a prior test already inserted into the shared throwaway DB (the same class
    of non-idempotent-test-data bug caught earlier building the CSV importer's tests). Tests
    that specifically want to prove dedup call this once and reuse the returned object."""
    raw = (FIXTURES_DIR / name).read_text()
    msg = email.message_from_string(raw)
    return FetchedEmail(
        message_id=f"<{uuid.uuid4().hex}@test.magpie.invalid>",
        sender=email.utils.parseaddr(msg.get("From", ""))[1],
        subject=str(msg.get("Subject", "")),
        body=_plaintext_body(msg),
        raw=raw,
        received_at=parsedate_to_datetime(msg.get("Date")),
    )


def _unique_email() -> str:
    return f"ingest-test-{uuid.uuid4().hex[:8]}@magpie.test"


async def _make_user_with_account(last4: str) -> tuple[uuid.UUID, uuid.UUID]:
    async with AsyncSessionLocal() as db:
        user = User(name="Ingest Test", email=_unique_email())
        db.add(user)
        await db.flush()
        account = Account(
            user_id=user.id, name="Card", institution="Test Bank", type="card", last4=last4
        )
        db.add(account)
        await db.commit()
        return user.id, account.id


async def test_amex_purchase_email_becomes_a_pending_spend_transaction():
    user_id, account_id = await _make_user_with_account("0000")
    fetcher = FakeImapFetcher([_load_eml("amex_large_purchase.eml")])

    async with AsyncSessionLocal() as db:
        summary = await run_ingest_poll(db, user_id, fetcher)

    assert summary.fetched == 1
    assert summary.created == 1
    assert summary.duplicate == 0
    assert summary.unparsed == 0

    async with AsyncSessionLocal() as db:
        result = await db.execute(Transaction.__table__.select())
        rows = [r for r in result.mappings().all() if r["account_id"] == account_id]
    assert len(rows) == 1
    txn = rows[0]
    assert txn["amount"] == -4200
    assert txn["kind"] == "spend"
    assert txn["status"] == "pending"
    assert txn["review_state"] == "needs_review"
    assert txn["source"] == "email"


async def test_usbank_zelle_email_becomes_a_pending_income_transaction():
    user_id, account_id = await _make_user_with_account("0000")
    fetcher = FakeImapFetcher([_load_eml("usbank_zelle_payment.eml")])

    async with AsyncSessionLocal() as db:
        await run_ingest_poll(db, user_id, fetcher)

    async with AsyncSessionLocal() as db:
        result = await db.execute(Transaction.__table__.select())
        rows = [r for r in result.mappings().all() if r["account_id"] == account_id]
    assert len(rows) == 1
    assert rows[0]["amount"] == 7500
    assert rows[0]["kind"] == "income"


async def test_reingesting_the_same_email_is_a_duplicate_not_a_second_transaction():
    user_id, account_id = await _make_user_with_account("0000")
    fetched_email = _load_eml("amex_large_purchase.eml")

    async with AsyncSessionLocal() as db:
        first = await run_ingest_poll(db, user_id, FakeImapFetcher([fetched_email]))
    async with AsyncSessionLocal() as db:
        second = await run_ingest_poll(db, user_id, FakeImapFetcher([fetched_email]))

    assert first.created == 1
    assert second.created == 0
    assert second.duplicate == 1

    async with AsyncSessionLocal() as db:
        result = await db.execute(Transaction.__table__.select())
        rows = [r for r in result.mappings().all() if r["account_id"] == account_id]
    assert len(rows) == 1  # still just one real transaction


async def test_unrecognized_subject_surfaces_as_unparsed_not_a_crash():
    user_id, _ = await _make_user_with_account("0000")
    fetcher = FakeImapFetcher([_load_eml("amex_unrecognized_subject.eml")])

    async with AsyncSessionLocal() as db:
        summary = await run_ingest_poll(db, user_id, fetcher)

    assert summary.created == 0
    assert summary.unparsed == 1

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            IngestEvent.__table__.select().where(IngestEvent.user_id == user_id)
        )
        rows = result.mappings().all()
    assert len(rows) == 1
    assert rows[0]["outcome"] == "unparsed"
    assert "never seen before" in rows[0]["raw_payload"]


async def test_no_matching_account_also_surfaces_as_unparsed():
    # An account exists, but its last4 doesn't match the fixture's "0000" hint.
    user_id, _ = await _make_user_with_account("9999")
    fetcher = FakeImapFetcher([_load_eml("amex_large_purchase.eml")])

    async with AsyncSessionLocal() as db:
        summary = await run_ingest_poll(db, user_id, fetcher)

    assert summary.created == 0
    assert summary.unparsed == 1


async def _make_user_with_two_accounts_sharing_last4(last4: str) -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        user = User(name="Ingest Test", email=_unique_email())
        db.add(user)
        await db.flush()
        db.add_all(
            [
                Account(user_id=user.id, name="Card", institution="Amex", type="card", last4=last4),
                Account(
                    user_id=user.id,
                    name="Checking",
                    institution="US Bank",
                    type="depository",
                    last4=last4,
                ),
            ]
        )
        await db.commit()
        return user.id


async def test_f16_last4_collision_degrades_to_unparsed_not_a_crash():
    # Two accounts legitimately share last4 "0000". The amex fixture's hint matches both — the
    # poll must not crash (scalar_one_or_none would raise MultipleResultsFound); it degrades to
    # unparsed and keeps going.
    user_id = await _make_user_with_two_accounts_sharing_last4("0000")
    fetcher = FakeImapFetcher([_load_eml("amex_large_purchase.eml")])

    async with AsyncSessionLocal() as db:
        summary = await run_ingest_poll(db, user_id, fetcher)

    assert summary.created == 0
    assert summary.unparsed == 1

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            IngestEvent.__table__.select().where(IngestEvent.user_id == user_id)
        )
        rows = result.mappings().all()
    assert len(rows) == 1
    assert rows[0]["outcome"] == "unparsed"
