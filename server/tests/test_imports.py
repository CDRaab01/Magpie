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
