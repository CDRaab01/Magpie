import datetime

from app.rules.alerts import should_alert
from app.rules.bill_matching import (
    BillCandidate,
    PaymentCandidate,
    find_bill_payment,
    is_bill_missing,
)


def test_finds_matching_payment_on_same_account_within_window():
    bill = BillCandidate("bill-1", "checking", 4500, datetime.date(2026, 7, 10))
    pool = [
        PaymentCandidate("p1", "checking", -4500, datetime.date(2026, 7, 12)),
        PaymentCandidate("p2", "amex", -4500, datetime.date(2026, 7, 10)),  # wrong account
    ]
    match = find_bill_payment(bill, pool)
    assert match is not None
    assert match.id == "p1"


def test_ignores_payment_on_a_different_account():
    bill = BillCandidate("bill-1", "checking", 4500, datetime.date(2026, 7, 10))
    pool = [PaymentCandidate("p1", "amex", -4500, datetime.date(2026, 7, 10))]
    assert find_bill_payment(bill, pool) is None


def test_ignores_payment_outside_window():
    bill = BillCandidate("bill-1", "checking", 4500, datetime.date(2026, 7, 10))
    pool = [PaymentCandidate("p1", "checking", -4500, datetime.date(2026, 7, 25))]
    assert find_bill_payment(bill, pool, window_days=10) is None


def test_ignores_wrong_amount():
    bill = BillCandidate("bill-1", "checking", 4500, datetime.date(2026, 7, 10))
    pool = [PaymentCandidate("p1", "checking", -1000, datetime.date(2026, 7, 10))]
    assert find_bill_payment(bill, pool) is None


def test_bill_missing_true_after_grace_window():
    assert is_bill_missing(datetime.date(2026, 7, 1), datetime.date(2026, 7, 10), grace_days=3)


def test_bill_missing_false_within_grace_window():
    assert not is_bill_missing(datetime.date(2026, 7, 1), datetime.date(2026, 7, 2), grace_days=3)


def test_should_alert_fires_only_on_rising_edge():
    assert should_alert(currently_true=True, previously_true=False)
    assert not should_alert(currently_true=True, previously_true=True)
    assert not should_alert(currently_true=False, previously_true=False)
    assert not should_alert(currently_true=False, previously_true=True)
