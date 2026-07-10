"""Monthly transaction export (ROADMAP #26) — a trust feature at near-zero cost: the escape hatch
that keeps the data the owner's. A plain CSV of one month's ledger, category names resolved, in
the same signed-cents-as-dollars convention the app displays.

The CSV assembly is pure (`rows_to_csv`) so it's table-testable; the service just gathers the
rows. Expired auth holds are excluded (they aren't money, `COUNTABLE_STATUSES`); split parents are
excluded and their child parts carry the category, matching every other rollup.
"""

import csv
import datetime
import io
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.category import Category
from app.models.transaction import COUNTABLE_STATUSES, Transaction

COLUMNS = ["date", "account", "merchant", "category", "kind", "amount", "status"]


def rows_to_csv(rows: list[dict]) -> str:
    """Serialize export rows to CSV text. `amount` is rendered as signed dollars (the display
    convention), everything else verbatim. Pure — no I/O, no DB."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow({**r, "amount": f"{r['amount_cents'] / 100:.2f}"})
    return buf.getvalue()


async def export_month_rows(
    db: AsyncSession, user_id: uuid.UUID, month: datetime.date
) -> list[dict]:
    """One month's transactions for this user, oldest first, category names resolved."""
    month_bucket = func.date_trunc("month", Transaction.date)
    result = await db.execute(
        select(
            Transaction.date,
            Account.name,
            func.coalesce(Transaction.merchant_norm, Transaction.merchant_raw),
            Category.name,
            Transaction.kind,
            Transaction.amount,
            Transaction.status,
        )
        .join(Account, Transaction.account_id == Account.id)
        .outerjoin(Category, Transaction.category_id == Category.id)
        .where(
            Account.user_id == user_id,
            Transaction.split_parent_id.is_(None),
            Transaction.status.in_(COUNTABLE_STATUSES),
            month_bucket == month.replace(day=1),
        )
        .order_by(Transaction.date, Transaction.created_at)
    )
    return [
        {
            "date": date.isoformat(),
            "account": account,
            "merchant": merchant or "",
            "category": category or "",
            "kind": kind,
            "amount_cents": amount,
            "status": status,
        }
        for date, account, merchant, category, kind, amount, status in result.all()
    ]


async def export_month_csv(db: AsyncSession, user_id: uuid.UUID, month: datetime.date) -> str:
    return rows_to_csv(await export_month_rows(db, user_id, month))
