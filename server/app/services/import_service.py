"""CSV reconciliation (CLAUDE.md Phase 3). Parses via the generic `app/imports/csv_parser.py`,
dedupes against existing transactions, and routes each new row through the rules engine
(Phase 5) — a CSV row's sign is a reliable direction signal but never a manual confirmation,
so unlike manual cash entries it can be auto-filed by a matched rule but never starts
pre-confirmed (CLAUDE.md's draft-confirm trust model).
"""

import datetime
import hashlib
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.imports.csv_parser import CsvParseError, ParsedCsvRow, parse_csv
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


async def _is_duplicate(db: AsyncSession, account_id: uuid.UUID, row: ParsedCsvRow) -> bool:
    """Dedup fingerprint for CSV rows (no message-id to key on, unlike email ingestion):
    an exact (account, date, amount, description) match is treated as the same transaction —
    re-importing the same file, or an overlapping date range, creates zero duplicates."""
    result = await db.execute(
        select(Transaction.id).where(
            Transaction.account_id == account_id,
            Transaction.date == row.date,
            Transaction.amount == row.amount_cents,
            Transaction.merchant_raw == row.description,
        )
    )
    return result.scalar_one_or_none() is not None


async def import_csv(
    db: AsyncSession,
    user_id: uuid.UUID,
    account_id: uuid.UUID,
    institution: str,
    file_bytes: bytes,
    *,
    now: datetime.datetime | None = None,
) -> ImportSummaryOut:
    now = now or datetime.datetime.now(datetime.timezone.utc)
    await _owned_account(db, user_id, account_id)

    try:
        text = file_bytes.decode("utf-8-sig")  # tolerate a BOM (common in bank CSV exports)
        rows = parse_csv(text)
    except (CsvParseError, UnicodeDecodeError) as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e))

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

    created = 0
    skipped = 0
    for row in rows:
        if await _is_duplicate(db, account_id, row):
            skipped += 1
            continue

        default_kind = "income" if row.amount_cents > 0 else "spend"
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
    batch.matched_count = 0  # reserved: matching a pending email-sourced row to a posted CSV
    # row is Phase 4 territory (pending/posted reconciliation), not this phase.
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
        matched_count=0,
        skipped_count=skipped,
        checkpoint_created=checkpoint_created,
    )
