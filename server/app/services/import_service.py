"""CSV reconciliation (CLAUDE.md Phase 3). Parses via the generic `app/imports/csv_parser.py`,
dedupes against existing transactions, and routes each new row through the rules engine
(Phase 5) — a CSV row's sign is a reliable direction signal but never a manual confirmation,
so unlike manual cash entries it can be auto-filed by a matched rule but never starts
pre-confirmed (CLAUDE.md's draft-confirm trust model).
"""

import datetime
import hashlib
import uuid
from dataclasses import replace

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.imports.csv_parser import CsvParseError, ParsedCsvRow, parse_csv
from app.imports.institution_mappings import default_kind_for, resolve_sign_flip
from app.imports.pending_match import PendingCandidate, find_pending_match
from app.models.account import Account
from app.models.import_batch import ImportBatch
from app.models.statement_checkpoint import StatementCheckpoint
from app.models.transaction import Transaction
from app.rules.merchant_match import normalize_merchant
from app.schemas.imports import ImportSummaryOut
from app.services.ai.llm_client import LmStudioClient
from app.services.rule_service import evaluate_transaction


async def _owned_account(db: AsyncSession, user_id: uuid.UUID, account_id: uuid.UUID) -> Account:
    result = await db.execute(
        select(Account).where(Account.id == account_id, Account.user_id == user_id)
    )
    account = result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")
    return account


def _fingerprint(row: ParsedCsvRow) -> tuple:
    """The CSV dedup key (no message-id to lean on, unlike email): (date, amount, description)
    identifies "the same transaction". Multiplicity matters — see `_existing_fingerprint_counts`."""
    return (row.date, row.amount_cents, row.description)


async def _existing_fingerprint_counts(db: AsyncSession, account_id: uuid.UUID) -> dict[tuple, int]:
    """How many transactions already exist per fingerprint on this account (F9), computed once
    per import. Counting — rather than a boolean "does any match" — is what lets a re-import stay
    idempotent AND two genuinely distinct same-day duplicates (two $5.00 coffees) both survive.
    The old boolean check skipped the second coffee, and worse, `scalar_one_or_none` *raised* on
    re-import once two identical rows already existed."""
    result = await db.execute(
        select(Transaction.date, Transaction.amount, Transaction.merchant_raw).where(
            Transaction.account_id == account_id
        )
    )
    counts: dict[tuple, int] = {}
    for date_, amount, merchant in result.all():
        key = (date_, amount, merchant)
        counts[key] = counts.get(key, 0) + 1
    return counts


async def _find_pending_email_match(
    db: AsyncSession, account_id: uuid.UUID, row: ParsedCsvRow
) -> Transaction | None:
    """The pending email-sourced transaction this CSV row reconciles (F4), or None. Transfers
    are excluded — a transfer leg's amount is half of a zero-sum pair and must not be rewritten
    to a CSV magnitude."""
    result = await db.execute(
        select(Transaction).where(
            Transaction.account_id == account_id,
            Transaction.status == "pending",
            Transaction.source == "email",
            Transaction.transfer_group.is_(None),
        )
    )
    candidates = [PendingCandidate(str(t.id), t.amount, t.date) for t in result.scalars().all()]
    match = find_pending_match(row.amount_cents, row.date, candidates)
    if match is None:
        return None
    found = await db.execute(select(Transaction).where(Transaction.id == uuid.UUID(match.id)))
    return found.scalar_one()


def _reconcile_pending_to_posted(
    txn: Transaction, row: ParsedCsvRow, batch_id: uuid.UUID, now: datetime.datetime
) -> None:
    """Promote a pending email swipe to the CSV's posted truth (F4). The CSV is authoritative for
    amount (tip/settlement), date, and merchant; the human/rule decision already on the row
    (kind, category, review_state, matched_rule_id) is preserved, and the email provenance
    (ingest_event_id) stays. Overwriting amount/date/merchant to the CSV values also keeps
    re-import idempotent: a second import of the same file now matches this row's dedup
    fingerprint and skips instead of creating a duplicate."""
    txn.status = "posted"
    txn.posted_at = now
    txn.amount = row.amount_cents
    txn.date = row.date
    txn.merchant_raw = row.description
    txn.merchant_norm = normalize_merchant(row.description) if row.description else None
    txn.import_batch_id = batch_id


async def import_csv(
    db: AsyncSession,
    user_id: uuid.UUID,
    account_id: uuid.UUID,
    institution: str,
    file_bytes: bytes,
    *,
    flip_sign: bool | None = None,
    now: datetime.datetime | None = None,
) -> ImportSummaryOut:
    now = now or datetime.datetime.now(datetime.timezone.utc)
    account = await _owned_account(db, user_id, account_id)

    try:
        text = file_bytes.decode("utf-8-sig")  # tolerate a BOM (common in bank CSV exports)
        rows = parse_csv(text)
    except (CsvParseError, UnicodeDecodeError) as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e))

    # F5: reconcile the file's sign convention with the ledger's (negative = outflow). Amex (and
    # other "positive amount = a charge" issuers) would otherwise import every charge as income and
    # every payment as spend — a whole card backfill inverted. Flip the amount (not the balance —
    # its convention is separate and unvalidated) when the institution default, or an explicit
    # per-import override, says so.
    if resolve_sign_flip(institution, flip_sign):
        rows = [replace(r, amount_cents=-r.amount_cents) for r in rows]

    # Oldest first, regardless of the file's own order (bank exports are often newest-first):
    # rule evaluation's cadence/observation logic assumes it sees history chronologically —
    # matters a lot for a 12-month backfill file containing many instances of one bill.
    rows = sorted(rows, key=lambda r: r.date)

    file_hash = hashlib.sha256(file_bytes).hexdigest()
    batch = ImportBatch(file_hash=file_hash, institution=institution, row_count=len(rows))
    db.add(batch)
    await db.flush()  # need batch.id before attaching rows to it

    # Only unmatched rows ever reach the AI stage (evaluate_transaction's stage 4), but a
    # 12-month backfill with many never-before-seen merchants can still mean many synchronous
    # LLM round-trips — a real latency tradeoff for bulk CSV import, not a correctness one.
    llm_client = (
        LmStudioClient(settings.llm_base_url, settings.llm_model) if settings.llm_base_url else None
    )

    # F9: dedup by multiplicity, not existence. Snapshot how many of each fingerprint already
    # exist, then let each file row consume one — so re-importing is idempotent while two truly
    # distinct same-day duplicates both survive. `consumed` counts how many existing rows this
    # file's rows have already matched.
    existing_counts = await _existing_fingerprint_counts(db, account_id)
    consumed: dict[tuple, int] = {}

    created = 0
    skipped = 0
    matched = 0
    for row in rows:
        # F4: if this posted CSV row is the same swipe as an email-sourced pending row already in
        # the ledger, merge into that one row rather than creating a second that would
        # double-count once reconciled. Checked before the exact-dup guard so the pending email
        # row is promoted, not the CSV row skipped.
        pending = await _find_pending_email_match(db, account_id, row)
        if pending is not None:
            _reconcile_pending_to_posted(pending, row, batch.id, now)
            await db.flush()
            matched += 1
            continue

        fp = _fingerprint(row)
        if consumed.get(fp, 0) < existing_counts.get(fp, 0):
            consumed[fp] = consumed.get(fp, 0) + 1
            skipped += 1
            continue

        # Card-aware kind (not just sign): on a card a positive amount is a payment (transfer) or
        # a refund, never income (institution_mappings.default_kind_for). A depository account
        # keeps the plain income/spend convention.
        default_kind = default_kind_for(account.type, row.amount_cents, row.description)
        evaluation = await evaluate_transaction(
            db,
            user_id,
            account_id=account_id,
            amount_cents=row.amount_cents,
            txn_date=row.date,
            merchant_raw=row.description,
            default_kind=default_kind,
            now=now,
            llm_client=llm_client,
        )
        db.add(
            Transaction(
                account_id=account_id,
                amount=row.amount_cents,
                currency="USD",
                date=row.date,
                status="posted",
                merchant_raw=row.description,
                merchant_norm=normalize_merchant(row.description) if row.description else None,
                kind=evaluation.kind,
                review_state=evaluation.review_state,
                category_id=evaluation.category_id,
                matched_rule_id=evaluation.matched_rule_id,
                rule_note=evaluation.rule_note,
                ai_suggested_category_id=evaluation.ai_suggested_category_id,
                transfer_group=evaluation.transfer_group,
                source="csv",
                import_batch_id=batch.id,
            )
        )
        # Flush (not commit) so this row is visible to the *next* row's rule evaluation within
        # the same batch — a 12-month backfill file may contain a dozen instances of one
        # recurring bill, and cold-start observation counting must see them as they're added.
        await db.flush()
        created += 1

    batch.created_count = created
    batch.matched_count = matched  # F4: pending email rows promoted to posted by this batch
    batch.skipped_count = skipped

    checkpoint_created = False
    balance_rows = [r for r in rows if r.balance_cents is not None]
    if balance_rows:
        last = max(balance_rows, key=lambda r: r.date)
        db.add(
            StatementCheckpoint(
                account_id=account_id,
                statement_date=last.date,
                stated_balance=last.balance_cents,
                import_batch_id=batch.id,
            )
        )
        checkpoint_created = True

    await db.commit()

    return ImportSummaryOut(
        row_count=len(rows),
        created_count=created,
        matched_count=matched,
        skipped_count=skipped,
        checkpoint_created=checkpoint_created,
    )
