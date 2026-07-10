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


# --- projected recurring bills (#24) ------------------------------------------------------

import uuid  # noqa: E402

from app.database import AsyncSessionLocal  # noqa: E402
from app.models.account import Account  # noqa: E402
from app.models.rule import Rule  # noqa: E402
from app.models.transaction import Transaction  # noqa: E402


def test_classify_carries_the_projected_flag():
    today = datetime.date(2026, 7, 1)
    bills = [BillInput("XCEL", 4500, datetime.date(2026, 7, 15), "Chk", is_projected=True)]
    out = classify_bills(bills, None, today)
    assert out[0].is_projected is True


async def _account_id(auth_client) -> str:
    return (
        await auth_client.post(
            "/accounts", json={"name": "Checking", "institution": "US Bank", "type": "depository"}
        )
    ).json()["id"]


async def _recurring_bill_rule(account_id: str, matcher: str, last_matched: datetime.date):
    async with AsyncSessionLocal() as db:
        acct = await db.get(Account, uuid.UUID(account_id))
        # A few observations so the projected amount has a median.
        for d, amt in ((30, -8000), (60, -8000), (90, -8200)):
            db.add(
                Transaction(
                    account_id=acct.id,
                    amount=amt,
                    date=last_matched - datetime.timedelta(days=d),
                    status="posted",
                    kind="spend",
                    source="csv",
                    merchant_raw=matcher,
                    merchant_norm=matcher,
                )
            )
        db.add(
            Rule(
                user_id=acct.user_id,
                type="recurring_bill",
                account_id=acct.id,
                matcher=matcher,
                cadence={"kind": "monthly"},
                last_matched_at=datetime.datetime.combine(
                    last_matched, datetime.time(), datetime.timezone.utc
                ),
                enabled=True,
            )
        )
        await db.commit()


async def test_a_recurring_bill_rule_projects_into_the_calendar(auth_client):
    account_id = await _account_id(auth_client)
    # Last paid ~3 weeks ago → monthly projection lands ~a week out, inside the horizon.
    await _recurring_bill_rule(
        account_id, "FRONTIER", datetime.date.today() - datetime.timedelta(days=22)
    )

    body = (await auth_client.get("/cashflow")).json()
    projected = [b for b in body["bills"] if b["is_projected"]]
    assert any(b["biller"] == "FRONTIER" for b in projected)
    frontier = next(b for b in projected if b["biller"] == "FRONTIER")
    assert frontier["amount_due_cents"] == 8000  # median of 8000/8000/8200


async def test_a_concrete_statement_suppresses_its_projection(auth_client):
    account_id = await _account_id(auth_client)
    await _recurring_bill_rule(
        account_id, "FRONTIER", datetime.date.today() - datetime.timedelta(days=22)
    )
    # A concrete unmatched statement for the same biller in the window — the real bill wins.
    future = (datetime.date.today() + datetime.timedelta(days=8)).isoformat()
    await auth_client.post(
        "/bills",
        json={
            "biller": "FRONTIER",
            "account_id": account_id,
            "amount_due": 8100,
            "due_date": future,
        },
    )

    body = (await auth_client.get("/cashflow")).json()
    frontier = [b for b in body["bills"] if b["biller"] == "FRONTIER"]
    assert len(frontier) == 1 and frontier[0]["is_projected"] is False  # only the concrete one
