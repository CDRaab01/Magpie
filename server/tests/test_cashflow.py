import datetime

from app.rules.cashflow import BillInput, classify_bills, next_paycheck_date


# --- pure projection ----------------------------------------------------------------------


def test_next_paycheck_is_the_soonest_across_income_rules():
    # biweekly from 2026-07-01 -> 07-15; monthly from 2026-07-20 -> 08-20. Soonest is 07-15.
    rules = [
        (datetime.date(2026, 7, 1), {"kind": "biweekly"}),
        (datetime.date(2026, 7, 20), {"kind": "monthly"}),
    ]
    assert next_paycheck_date(rules, datetime.date(2026, 7, 10)) == datetime.date(2026, 7, 15)


def test_next_paycheck_none_without_income_rules():
    assert next_paycheck_date([], datetime.date(2026, 7, 10)) is None


def test_malformed_cadence_is_skipped_not_fatal():
    rules = [
        (datetime.date(2026, 7, 1), {"kind": "nonsense"}),
        (datetime.date(2026, 7, 1), {"kind": "weekly"}),
    ]
    assert next_paycheck_date(rules, datetime.date(2026, 7, 1)) == datetime.date(2026, 7, 8)


def test_classify_sorts_and_flags_overdue_and_before_paycheck():
    today = datetime.date(2026, 7, 10)
    paycheck = datetime.date(2026, 7, 15)
    bills = [
        BillInput("XCEL", 4500, datetime.date(2026, 7, 12), "Checking"),  # before paycheck
        BillInput("RENT", 150000, datetime.date(2026, 7, 20), "Checking"),  # after paycheck
        BillInput("OLD", 1000, datetime.date(2026, 7, 5), "Checking"),  # overdue + before
    ]
    out = classify_bills(bills, paycheck, today)
    assert [b.biller for b in out] == ["OLD", "XCEL", "RENT"]  # sorted by due date
    assert out[0].is_overdue and out[0].before_next_paycheck  # OLD
    assert not out[1].is_overdue and out[1].before_next_paycheck  # XCEL
    assert not out[2].before_next_paycheck  # RENT is after the paycheck


def test_no_paycheck_means_nothing_flagged_before_paycheck():
    today = datetime.date(2026, 7, 10)
    bills = [BillInput("X", 100, datetime.date(2026, 7, 12), "A")]
    out = classify_bills(bills, None, today)
    assert out[0].before_next_paycheck is False


# --- endpoint -----------------------------------------------------------------------------


async def test_cashflow_endpoint_lists_unmatched_bills_sorted(auth_client):
    acct = (
        await auth_client.post(
            "/accounts", json={"name": "Checking", "institution": "US Bank", "type": "depository"}
        )
    ).json()["id"]
    today = datetime.date.today()
    future = (today + datetime.timedelta(days=20)).isoformat()
    overdue = (today - datetime.timedelta(days=10)).isoformat()
    await auth_client.post(
        "/bills",
        json={"biller": "RENT", "account_id": acct, "amount_due": 150000, "due_date": future},
    )
    await auth_client.post(
        "/bills",
        json={"biller": "XCEL", "account_id": acct, "amount_due": 4500, "due_date": overdue},
    )

    r = await auth_client.get("/cashflow")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["next_paycheck_date"] is None  # no income rule configured
    assert [b["biller"] for b in body["bills"]] == ["XCEL", "RENT"]  # overdue first
    assert body["bills"][0]["is_overdue"] is True
    assert all(b["before_next_paycheck"] is False for b in body["bills"])  # no paycheck to beat
    assert body["total_due_before_paycheck_cents"] == 0
