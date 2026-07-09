"""Wave 1 read models: the pure trend series + the four /summary endpoints."""

import datetime

from app.ledger.rollups import DatedForSeries, rollup_month_series

# --- pure: rollup_month_series ------------------------------------------------------------


def test_series_returns_a_dense_bucket_per_requested_month_in_order():
    txns = [
        DatedForSeries(2026, 5, "income", 500000),
        DatedForSeries(2026, 5, "spend", -20000),
        DatedForSeries(2026, 7, "spend", -3000),
    ]
    months = [(2026, 5), (2026, 6), (2026, 7)]
    out = rollup_month_series(txns, months)

    assert [(m.year, m.month) for m in out] == months  # order + density preserved
    assert out[0].income_cents == 500000 and out[0].spend_cents == -20000
    assert out[0].net_cents == 480000
    assert out[1].income_cents == 0 and out[1].spend_cents == 0  # June: no activity, still present
    assert out[2].spend_cents == -3000


def test_series_excludes_transfers_and_nets_refunds_into_spend():
    txns = [
        DatedForSeries(2026, 7, "spend", -10000),
        DatedForSeries(2026, 7, "refund", 2500),  # nets spend down, never counts as income
        DatedForSeries(2026, 7, "transfer", -99999),  # internal movement, excluded entirely
    ]
    out = rollup_month_series(txns, [(2026, 7)])
    assert out[0].spend_cents == -7500
    assert out[0].income_cents == 0
    assert out[0].net_cents == -7500


def test_series_ignores_rows_outside_the_requested_window():
    txns = [DatedForSeries(2025, 1, "spend", -50000)]  # long before the window
    out = rollup_month_series(txns, [(2026, 7)])
    assert out[0].spend_cents == 0


# --- endpoints ----------------------------------------------------------------------------


async def _account(auth_client, type_="depository", name="Checking", institution="US Bank"):
    r = await auth_client.post(
        "/accounts", json={"name": name, "institution": institution, "type": type_}
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _txn(auth_client, account_id, amount, kind, *, date, merchant=None, category_id=None):
    body = {
        "account_id": account_id,
        "amount": amount,
        "kind": kind,
        "date": date,
        "currency": "USD",
        "status": "posted",
    }
    if merchant is not None:
        body["merchant_raw"] = merchant
    if category_id is not None:
        body["category_id"] = category_id
    r = await auth_client.post("/transactions", json=body)
    assert r.status_code == 201, r.text
    return r.json()


async def test_history_returns_requested_number_of_months_oldest_first(auth_client):
    acct = await _account(auth_client)
    today = datetime.date.today()
    await _txn(auth_client, acct, -4500, "spend", date=today.isoformat())

    r = await auth_client.get("/summary/history?months=3")
    assert r.status_code == 200, r.text
    months = r.json()["months"]
    assert len(months) == 3
    # oldest first, and the current month is the last bucket
    assert (months[-1]["year"], months[-1]["month"]) == (today.year, today.month)
    assert months[-1]["spend_cents"] == -4500
    assert months[0]["spend_cents"] == 0  # an earlier month with no activity is still present


async def test_categories_breakdown_sorts_largest_spend_first(auth_client):
    acct = await _account(auth_client)
    cats = (await auth_client.get("/categories")).json()
    groceries = next(c["id"] for c in cats if c["name"] == "Groceries")
    dining = next(c["id"] for c in cats if c["name"] == "Dining")
    today = datetime.date.today()
    month = today.replace(day=1).isoformat()

    await _txn(auth_client, acct, -3000, "spend", date=today.isoformat(), category_id=dining)
    await _txn(auth_client, acct, -12000, "spend", date=today.isoformat(), category_id=groceries)
    # An uncategorized spend lands in its own bucket.
    await _txn(auth_client, acct, -500, "spend", date=today.isoformat())

    r = await auth_client.get(f"/summary/categories?month={month}")
    assert r.status_code == 200, r.text
    items = r.json()["categories"]
    assert items[0]["category_name"] == "Groceries"  # -12000, largest spend
    assert items[0]["spend_cents"] == -12000
    assert items[1]["category_name"] == "Dining"
    uncategorized = next(i for i in items if i["category_id"] is None)
    assert uncategorized["category_name"] == "Uncategorized"
    assert uncategorized["spend_cents"] == -500


async def test_top_merchants_aggregates_and_ranks_by_spend(auth_client):
    acct = await _account(auth_client)
    today = datetime.date.today()
    month = today.replace(day=1).isoformat()
    # Two swipes at the same merchant aggregate; a bigger single swipe outranks them.
    await _txn(auth_client, acct, -1000, "spend", date=today.isoformat(), merchant="COFFEE BAR")
    await _txn(auth_client, acct, -1500, "spend", date=today.isoformat(), merchant="COFFEE BAR")
    await _txn(auth_client, acct, -9000, "spend", date=today.isoformat(), merchant="BIG BOX")

    r = await auth_client.get(f"/summary/merchants?month={month}")
    assert r.status_code == 200, r.text
    merchants = r.json()["merchants"]
    assert merchants[0]["merchant"] == "BIG BOX"
    assert merchants[0]["spend_cents"] == -9000
    coffee = next(m for m in merchants if m["merchant"] == "COFFEE BAR")
    assert coffee["spend_cents"] == -2500  # aggregated
    assert coffee["transaction_count"] == 2


async def test_safe_to_spend_is_depository_balance_minus_bills_before_paycheck(auth_client):
    acct = await _account(auth_client)
    today = datetime.date.today()
    # Anchor the balance with a checkpoint, then income on top → a clean known balance.
    await _txn(auth_client, acct, 200000, "income", date=today.isoformat())

    r = await auth_client.get("/summary/safe-to-spend")
    assert r.status_code == 200, r.text
    body = r.json()
    # No checkpoint, so the balance is the plain signed sum; no bills, so nothing set aside.
    assert body["depository_balance_cents"] == 200000
    assert body["due_before_paycheck_cents"] == 0
    assert body["safe_to_spend_cents"] == 200000
    assert body["next_paycheck_date"] is None


async def test_safe_to_spend_excludes_card_balances(auth_client):
    depository = await _account(auth_client, type_="depository", name="Checking")
    card = await _account(auth_client, type_="card", name="Amex", institution="Amex")
    today = datetime.date.today()
    await _txn(auth_client, depository, 50000, "income", date=today.isoformat())
    await _txn(auth_client, card, -30000, "spend", date=today.isoformat())  # card debt, excluded

    r = await auth_client.get("/summary/safe-to-spend")
    body = r.json()
    assert body["depository_balance_cents"] == 50000  # the card's -30000 is not counted


async def test_summary_endpoints_require_auth(client):
    for path in (
        "/summary/history",
        f"/summary/categories?month={datetime.date.today().replace(day=1).isoformat()}",
        f"/summary/merchants?month={datetime.date.today().replace(day=1).isoformat()}",
        "/summary/safe-to-spend",
    ):
        r = await client.get(path)
        assert r.status_code == 401, f"{path} -> {r.status_code}"
