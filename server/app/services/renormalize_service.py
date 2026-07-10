"""Recompute `merchant_norm` from `merchant_raw` with today's normalizer (ROADMAP #25a).

`merchant_norm` is a *derived* comparison key for rules, not a financial fact — no amount, date,
kind, category or review_state is touched here. But it is written once at ingest/import time, so a
row imported before a normalizer change carries a stale key forever. This has bitten the project
three times (parser `parse_version`, the pre-deploy CSV import, `merchant_norm` itself); each time
the *code* was right and the *data* was computed by yesterday's code. The parser-replay tool cashes
that promise for `ingest_events`; this is its equivalent for `merchant_norm`, so the next stale-key
recompute is one dry-run call instead of a bespoke script nobody has reviewed.

Safe by construction: `normalize_merchant` is idempotent (pinned by tests), so re-running changes
nothing the second time; and a row is never allowed to normalize to an empty key (that would
silently break rule matching), which aborts the run rather than corrupting the ledger.

`dry_run=True` is the default and rolls the recompute back, so the report describes exactly what a
real run would do because it did it.
"""

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.transaction import Transaction
from app.rules.merchant_match import normalize_merchant

SAMPLE_LIMIT = 40


@dataclass(frozen=True)
class RenormalizeChange:
    old: str | None
    new: str
    count: int  # how many rows made this same old->new transition


@dataclass(frozen=True)
class RenormalizeSummary:
    dry_run: bool
    examined: int
    changed: int
    distinct_before: int
    distinct_after: int
    sample: list[RenormalizeChange] = field(default_factory=list)


async def renormalize_merchants(
    db: AsyncSession, user_id: uuid.UUID, *, dry_run: bool = True
) -> RenormalizeSummary:
    """Recompute every transaction's `merchant_norm` for this user. Returns a report; writes only
    when `dry_run` is False. Aborts (raising ValueError) if any row would normalize to empty,
    before committing anything."""
    rows = (
        (
            await db.execute(
                select(Transaction)
                .join(Account, Transaction.account_id == Account.id)
                .where(Account.user_id == user_id, Transaction.merchant_raw.is_not(None))
            )
        )
        .scalars()
        .all()
    )

    before: set[str | None] = set()
    after: set[str] = set()
    transitions: dict[tuple[str | None, str], int] = {}
    changed = 0

    for txn in rows:
        old = txn.merchant_norm
        new = normalize_merchant(txn.merchant_raw)
        before.add(old)
        after.add(new)
        if not new:
            # A blank key can't match any rule — a normalizer that empties a real merchant is a
            # bug, and applying it would silently break matching. Refuse the whole run.
            raise ValueError(
                f"Refusing to renormalize: {txn.merchant_raw!r} would become an empty key"
            )
        if old != new:
            transitions[(old, new)] = transitions.get((old, new), 0) + 1
            changed += 1
            txn.merchant_norm = new

    if dry_run:
        await db.rollback()
    else:
        await db.commit()

    sample = [
        RenormalizeChange(old=old, new=new, count=n)
        for (old, new), n in sorted(transitions.items(), key=lambda kv: -kv[1])[:SAMPLE_LIMIT]
    ]
    return RenormalizeSummary(
        dry_run=dry_run,
        examined=len(rows),
        changed=changed,
        distinct_before=len(before),
        distinct_after=len(after),
        sample=sample,
    )
