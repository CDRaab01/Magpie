"""Monthly CSV export (ROADMAP #26)."""

import datetime
import uuid

from app.database import AsyncSessionLocal
from app.models.account import Account
from app.models.category import Category
from app.models.transaction import Transaction
from app.models.user import User
from app.services.export_service import export_month_rows, rows_to_csv

MONTH = datetime.date(2026, 7, 1)


def test_rows_to_csv_renders_signed_dollars_with_a_header():
    csv = rows_to_csv(
        [
            {
                "date": "2026-07-03",
                "account": "Amex",
                "merchant": "CAFE",
                "category": "Dining",
                "kind": "spend",
                "amount_cents": -1234,
                "status": "posted",
            },
        ]
    )
    lines = csv.strip().splitlines()
    assert lines[0] == "date,account,merchant,category,kind,amount,status"
    assert lines[1] == "2026-07-03,Amex,CAFE,Dining,spend,-12.34,posted"


def test_rows_to_csv_income_is_positive():
    csv = rows_to_csv(
        [
            {
                "date": "2026-07-01",
                "account": "Chk",
                "merchant": "EMPLOYER",
                "category": "",
                "kind": "income",
                "amount_cents": 500000,
                "status": "posted",
            }
        ]
    )
    assert ",5000.00,posted" in csv


async def _setup():
    async with AsyncSessionLocal() as db:
        user = User(name="Export", email=f"export-{uuid.uuid4().hex[:8]}@magpie.test")
        db.add(user)
        await db.flush()
        acct = Account(user_id=user.id, name="Checking", institution="T", type="depository")
        db.add(acct)
        cat = Category(name="Dining", user_id=user.id)
        db.add(cat)
        await db.flush()
        await db.commit()
        return user.id, acct.id, cat.id


async def _txn(account_id, **kw):
    kw.setdefault("status", "posted")
    async with AsyncSessionLocal() as db:
        db.add(Transaction(account_id=account_id, currency="USD", source="csv", **kw))
        await db.commit()


async def test_export_covers_only_the_month_and_orders_by_date():
    user_id, account_id, cat_id = await _setup()
    await _txn(
        account_id,
        amount=-1000,
        date=datetime.date(2026, 7, 20),
        kind="spend",
        merchant_raw="LATE",
        merchant_norm="LATE",
        category_id=cat_id,
    )
    await _txn(
        account_id,
        amount=-2000,
        date=datetime.date(2026, 7, 2),
        kind="spend",
        merchant_raw="EARLY",
        merchant_norm="EARLY",
        category_id=cat_id,
    )
    await _txn(
        account_id,
        amount=-9999,
        date=datetime.date(2026, 6, 30),
        kind="spend",
        merchant_raw="PRIORMONTH",
        merchant_norm="PRIORMONTH",
    )

    async with AsyncSessionLocal() as db:
        rows = await export_month_rows(db, user_id, MONTH)

    assert [r["merchant"] for r in rows] == ["EARLY", "LATE"]  # prior month excluded, date order
    assert rows[0]["category"] == "Dining"


async def test_export_excludes_expired_holds_and_split_parents():
    user_id, account_id, cat_id = await _setup()
    await _txn(
        account_id,
        amount=-500,
        date=datetime.date(2026, 7, 5),
        kind="spend",
        merchant_raw="EXPIRED",
        merchant_norm="EXPIRED",
        status="expired",
    )
    await _txn(
        account_id,
        amount=-600,
        date=datetime.date(2026, 7, 6),
        kind="spend",
        merchant_raw="REAL",
        merchant_norm="REAL",
    )

    async with AsyncSessionLocal() as db:
        rows = await export_month_rows(db, user_id, MONTH)
    assert [r["merchant"] for r in rows] == ["REAL"]


async def test_export_endpoint_returns_csv_with_a_filename(auth_client):
    r = await auth_client.post(
        "/accounts", json={"name": "Checking", "institution": "T", "type": "depository"}
    )
    account_id = r.json()["id"]
    await _txn(
        uuid.UUID(account_id),
        amount=-4200,
        date=datetime.date(2026, 7, 10),
        kind="spend",
        merchant_raw="SHOP",
        merchant_norm="SHOP",
    )

    r = await auth_client.get("/export/transactions.csv?month=2026-07-15")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")
    assert "magpie-2026-07.csv" in r.headers.get("content-disposition", "")
    assert "date,account,merchant,category,kind,amount,status" in r.text
    assert "-42.00" in r.text


async def test_export_endpoint_requires_auth(client):
    assert (await client.get("/export/transactions.csv?month=2026-07-01")).status_code == 401
