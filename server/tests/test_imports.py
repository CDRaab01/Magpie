import io


async def _make_account(auth_client):
    r = await auth_client.post(
        "/accounts", json={"name": "Checking", "institution": "US Bank", "type": "depository"}
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _csv_file(text: str, name: str = "statement.csv"):
    return {"file": (name, io.BytesIO(text.encode()), "text/csv")}


async def test_import_creates_transactions(auth_client):
    account_id = await _make_account(auth_client)
    csv_text = (
        "Date,Description,Amount\n2026-07-01,Coffee Shop,-4.50\n2026-07-05,Paycheck,1500.00\n"
    )
    r = await auth_client.post(
        "/imports/csv",
        data={"account_id": account_id, "institution": "US Bank"},
        files=_csv_file(csv_text),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["row_count"] == 2
    assert body["created_count"] == 2
    assert body["skipped_count"] == 0
    assert body["checkpoint_created"] is False

    r = await auth_client.get("/transactions")
    assert len(r.json()) == 2
    kinds = {t["kind"] for t in r.json()}
    assert kinds == {"income", "spend"}
    sources = {t["source"] for t in r.json()}
    assert sources == {"csv"}
    review_states = {t["review_state"] for t in r.json()}
    assert review_states == {"needs_review"}


async def test_import_batch_is_scoped_to_the_user(auth_client):
    """#7: the batch a CSV import creates carries its owner, so `import_batches` is no longer the
    one unscoped table."""
    import uuid as _uuid

    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.account import Account
    from app.models.import_batch import ImportBatch

    account_id = await _make_account(auth_client)
    await auth_client.post(
        "/imports/csv",
        data={"account_id": account_id, "institution": "US Bank"},
        files=_csv_file("Date,Description,Amount\n2026-07-01,Coffee,-4.50\n"),
    )
    async with AsyncSessionLocal() as db:
        acct = await db.get(Account, _uuid.UUID(account_id))
        batches = (
            await db.execute(select(ImportBatch).where(ImportBatch.user_id == acct.user_id))
        ).scalars().all()
    assert len(batches) == 1  # this fresh user's single import, correctly attributed


async def test_amex_positive_charge_imports_as_spend_not_income(auth_client):
    # F5: Amex exports a charge as a POSITIVE amount. Without the per-institution sign flip this
    # would book the charge as income (and a payment as spend) — a whole card backfill inverted.
    r = await auth_client.post(
        "/accounts", json={"name": "Amex", "institution": "American Express", "type": "card"}
    )
    account_id = r.json()["id"]
    # Amex convention: a charge is positive, a payment/credit is negative.
    csv_text = (
        "Date,Description,Amount\n"
        "2026-07-01,TEST MERCHANT CO,42.00\n"
        "2026-07-05,ONLINE PAYMENT,-100.00\n"
    )
    r = await auth_client.post(
        "/imports/csv",
        data={"account_id": account_id, "institution": "American Express"},
        files=_csv_file(csv_text),
    )
    assert r.status_code == 200, r.text
    by_merchant = {t["merchant_raw"]: t for t in (await auth_client.get("/transactions")).json()}
    charge = by_merchant["TEST MERCHANT CO"]
    assert charge["amount"] == -4200 and charge["kind"] == "spend"  # flipped to an outflow
    assert by_merchant["ONLINE PAYMENT"]["amount"] == 10000  # flipped to an inflow


async def test_card_payment_is_transfer_and_credit_is_refund_never_income(auth_client):
    # From the real Amex backfill: a credit card never has income. After the sign flip a positive
    # amount is a PAYMENT (transfer) if its description looks like one, else a REFUND — never income.
    r = await auth_client.post(
        "/accounts", json={"name": "Amex", "institution": "American Express", "type": "card"}
    )
    account_id = r.json()["id"]
    csv_text = (
        "Date,Description,Amount\n"
        "2026-07-01,TEST MERCHANT CO,42.00\n"  # charge -> spend
        "2026-07-05,MOBILE PAYMENT - THANK YOU,-500.00\n"  # payment -> transfer
        "2026-07-06,SOME STORE REFUND,-9.00\n"  # merchant credit -> refund
    )
    r = await auth_client.post(
        "/imports/csv",
        data={"account_id": account_id, "institution": "American Express"},
        files=_csv_file(csv_text),
    )
    assert r.status_code == 200, r.text
    by = {t["merchant_raw"]: t for t in (await auth_client.get("/transactions")).json()}
    assert by["TEST MERCHANT CO"]["kind"] == "spend"
    assert by["MOBILE PAYMENT - THANK YOU"]["kind"] == "transfer"
    assert by["SOME STORE REFUND"]["kind"] == "refund"
    assert all(t["kind"] != "income" for t in by.values())  # nothing booked as income


async def test_discover_format_parses_and_classifies(auth_client):
    # Discover: two date columns ("Trans. Date"/"Post Date") + a Category column, positive=charge,
    # "INTERNET PAYMENT - THANK YOU" negative. Confirmed against a real 24-month export 2026-07-09.
    r = await auth_client.post(
        "/accounts", json={"name": "Discover", "institution": "Discover", "type": "card"}
    )
    account_id = r.json()["id"]
    csv_text = (
        "Trans. Date,Post Date,Description,Amount,Category\n"
        "07/01/2026,07/02/2026,TEST CAFE USA,41.87,Merchandise\n"
        "07/08/2026,07/08/2026,INTERNET PAYMENT - THANK YOU,-450.18,Payments and Credits\n"
    )
    r = await auth_client.post(
        "/imports/csv",
        data={"account_id": account_id, "institution": "Discover"},
        files=_csv_file(csv_text),
    )
    assert r.status_code == 200, r.text
    by = {t["merchant_raw"]: t for t in (await auth_client.get("/transactions")).json()}
    assert by["TEST CAFE USA"]["amount"] == -4187 and by["TEST CAFE USA"]["kind"] == "spend"
    payment = by["INTERNET PAYMENT - THANK YOU"]
    assert payment["amount"] == 45018 and payment["kind"] == "transfer"


async def test_reimporting_the_same_file_creates_zero_duplicates(auth_client):
    account_id = await _make_account(auth_client)
    csv_text = "Date,Description,Amount\n2026-07-01,Coffee Shop,-4.50\n"

    r1 = await auth_client.post(
        "/imports/csv",
        data={"account_id": account_id, "institution": "US Bank"},
        files=_csv_file(csv_text),
    )
    assert r1.json()["created_count"] == 1

    r2 = await auth_client.post(
        "/imports/csv",
        data={"account_id": account_id, "institution": "US Bank"},
        files=_csv_file(csv_text),
    )
    assert r2.json()["created_count"] == 0
    assert r2.json()["skipped_count"] == 1

    r = await auth_client.get("/transactions")
    assert len(r.json()) == 1  # still just one real transaction


async def test_two_identical_same_day_rows_both_survive(auth_client):
    # F9: two genuinely distinct same-day charges (two $5.00 coffees) must NOT collapse into one.
    account_id = await _make_account(auth_client)
    csv_text = "Date,Description,Amount\n2026-07-01,Coffee,-5.00\n2026-07-01,Coffee,-5.00\n"
    r = await auth_client.post(
        "/imports/csv",
        data={"account_id": account_id, "institution": "US Bank"},
        files=_csv_file(csv_text),
    )
    assert r.json()["created_count"] == 2  # both survive, not deduped to one
    assert len((await auth_client.get("/transactions")).json()) == 2

    # Re-importing is still idempotent AND must not crash now that two identical rows exist
    # (the old scalar_one_or_none raised MultipleResultsFound on exactly this).
    r2 = await auth_client.post(
        "/imports/csv",
        data={"account_id": account_id, "institution": "US Bank"},
        files=_csv_file(csv_text),
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["created_count"] == 0 and r2.json()["skipped_count"] == 2
    assert len((await auth_client.get("/transactions")).json()) == 2


async def test_partial_duplicate_import_creates_only_the_new_occurrence(auth_client):
    # F9 multiplicity: DB has one coffee; a file with two coffees adds exactly one more.
    account_id = await _make_account(auth_client)
    one = "Date,Description,Amount\n2026-07-01,Coffee,-5.00\n"
    await auth_client.post(
        "/imports/csv",
        data={"account_id": account_id, "institution": "US Bank"},
        files=_csv_file(one),
    )
    two = "Date,Description,Amount\n2026-07-01,Coffee,-5.00\n2026-07-01,Coffee,-5.00\n"
    r = await auth_client.post(
        "/imports/csv",
        data={"account_id": account_id, "institution": "US Bank"},
        files=_csv_file(two),
    )
    assert r.json()["created_count"] == 1 and r.json()["skipped_count"] == 1
    assert len((await auth_client.get("/transactions")).json()) == 2


async def test_overlapping_date_range_only_creates_new_rows(auth_client):
    account_id = await _make_account(auth_client)
    first = "Date,Description,Amount\n2026-07-01,Coffee,-4.50\n2026-07-02,Lunch,-12.00\n"
    r1 = await auth_client.post(
        "/imports/csv",
        data={"account_id": account_id, "institution": "US Bank"},
        files=_csv_file(first),
    )
    assert r1.json()["created_count"] == 2

    # Overlaps July 2 (duplicate) and adds July 3 (new).
    second = "Date,Description,Amount\n2026-07-02,Lunch,-12.00\n2026-07-03,Dinner,-20.00\n"
    r2 = await auth_client.post(
        "/imports/csv",
        data={"account_id": account_id, "institution": "US Bank"},
        files=_csv_file(second),
    )
    assert r2.json()["created_count"] == 1
    assert r2.json()["skipped_count"] == 1

    r = await auth_client.get("/transactions")
    assert len(r.json()) == 3


async def test_balance_column_creates_a_statement_checkpoint(auth_client):
    account_id = await _make_account(auth_client)
    csv_text = (
        "Date,Description,Amount,Balance\n"
        "2026-07-01,Coffee,-4.50,995.50\n"
        "2026-07-02,Lunch,-12.00,983.50\n"
    )
    r = await auth_client.post(
        "/imports/csv",
        data={"account_id": account_id, "institution": "US Bank"},
        files=_csv_file(csv_text),
    )
    assert r.json()["checkpoint_created"] is True

    accounts = await auth_client.get("/accounts")
    account = next(a for a in accounts.json() if a["id"] == account_id)
    # F1: the import's checkpoint (983.50 as of 2026-07-02) anchors the account. Both rows are
    # dated on/before the checkpoint, so they're already inside the stated balance — the derived
    # balance IS the stated balance, and a single checkpoint reconciles to zero.
    assert account["balance_cents"] == 98350
    assert account["balance_delta_cents"] == 0


async def test_two_month_backfill_reconciles_to_zero_despite_unknown_prior_history(auth_client):
    # The F1 acceptance case through the real import path: import two consecutive months of an
    # account whose balance before month one is unknown to the ledger. The first checkpoint is
    # the only truth about the starting balance; the second must still reconcile to zero, and
    # the derived balance must equal the latest stated balance — not the net of the rows.
    account_id = await _make_account(auth_client)

    may = (
        "Date,Description,Amount,Balance\n"
        "2026-05-15,Groceries,-50.00,950.00\n"
        "2026-05-31,Paycheck,50.00,1000.00\n"  # checkpoint: 1000.00 as of 2026-05-31
    )
    r1 = await auth_client.post(
        "/imports/csv",
        data={"account_id": account_id, "institution": "US Bank"},
        files=_csv_file(may, name="may.csv"),
    )
    assert r1.json()["checkpoint_created"] is True

    june = (
        "Date,Description,Amount,Balance\n"
        "2026-06-05,Rent,-300.00,700.00\n"
        "2026-06-20,Paycheck,500.00,1200.00\n"  # checkpoint: 1200.00 as of 2026-06-20
    )
    r2 = await auth_client.post(
        "/imports/csv",
        data={"account_id": account_id, "institution": "US Bank"},
        files=_csv_file(june, name="june.csv"),
    )
    assert r2.json()["checkpoint_created"] is True

    accounts = await auth_client.get("/accounts")
    account = next(a for a in accounts.json() if a["id"] == account_id)
    # Anchored at May's 1000.00, plus June's net (+200.00) ⇒ 1200.00, matching June's statement.
    assert account["balance_cents"] == 120000
    # Ledger fully accounts for the movement between the two checkpoints ⇒ the honesty meter is 0.
    assert account["balance_delta_cents"] == 0


async def test_no_balance_column_leaves_delta_none(auth_client):
    account_id = await _make_account(auth_client)
    csv_text = "Date,Description,Amount\n2026-07-01,Coffee,-4.50\n"
    await auth_client.post(
        "/imports/csv",
        data={"account_id": account_id, "institution": "US Bank"},
        files=_csv_file(csv_text),
    )
    accounts = await auth_client.get("/accounts")
    account = next(a for a in accounts.json() if a["id"] == account_id)
    assert account["balance_delta_cents"] is None
    assert account["balance_cents"] == -450


async def test_import_rejects_unknown_account(auth_client):
    csv_text = "Date,Description,Amount\n2026-07-01,Coffee,-4.50\n"
    r = await auth_client.post(
        "/imports/csv",
        data={"account_id": "00000000-0000-0000-0000-000000000000", "institution": "X"},
        files=_csv_file(csv_text),
    )
    assert r.status_code == 404


async def test_import_rejects_unparseable_csv(auth_client):
    account_id = await _make_account(auth_client)
    r = await auth_client.post(
        "/imports/csv",
        data={"account_id": account_id, "institution": "US Bank"},
        files=_csv_file("not,even,a,real,statement\njust,some,text\n"),
    )
    assert r.status_code == 422
