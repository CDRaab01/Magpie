"""CSV reconciliation (CLAUDE.md Phase 3). Parses via the generic `app/imports/csv_parser.py`,
dedupes against existing transactions, and creates a needs_review draft per new row — CSV
rows are a best-effort kind guess (sign only), never a manual confirmation, so unlike manual
cash entries they start in review, not confirmed (CLAUDE.md's draft-confirm trust model).
"""

import hashlib
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.imports.csv_parser import CsvParseError, ParsedCsvRow, parse_csv
from app.models.account import Account
from app.models.import_batch import ImportBatch
from app.models.statement_checkpoint import StatementCheckpoint
from app.models.transaction import Transaction
from app.schemas.imports import ImportSummaryOut


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
) -> ImportSummaryOut:
    await _owned_account(db, user_id, account_id)

    try:
        text = file_bytes.decode("utf-8-sig")  # tolerate a BOM (common in bank CSV exports)
        rows = parse_csv(text)
    except (CsvParseError, UnicodeDecodeError) as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e))

    file_hash = hashlib.sha256(file_bytes).hexdigest()
    batch = ImportBatch(file_hash=file_hash, institution=institution, row_count=len(rows))
    db.add(batch)
    await db.flush()  # need batch.id before attaching rows to it

    created = 0
    skipped = 0
    for row in rows:
        if await _is_duplicate(db, account_id, row):
            skipped += 1
            continue
        db.add(
            Transaction(
                account_id=account_id,
                amount=row.amount_cents,
                currency="USD",
                date=row.date,
                status="posted",
                merchant_raw=row.description,
                # Sign-only guess — CSV rows carry no reliable kind signal beyond direction
                # until the rules engine (Phase 5) can classify by merchant/cadence.
                kind="income" if row.amount_cents > 0 else "spend",
                review_state="needs_review",
                source="csv",
                import_batch_id=batch.id,
            )
        )
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
