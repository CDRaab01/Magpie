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
        PaymentCandidate("p1", "checking", -4500, datetime.date(2026, 7, 12), "spend"),
        PaymentCandidate("p2", "amex", -4500, datetime.date(2026, 7, 10), "spend"),  # wrong account
    ]
    match = find_bill_payment(bill, pool)
    assert match is not None
    assert match.id == "p1"


def test_ignores_payment_on_a_different_account():
    bill = BillCandidate("bill-1", "checking", 4500, datetime.date(2026, 7, 10))
    pool = [PaymentCandidate("p1", "amex", -4500, datetime.date(2026, 7, 10), "spend")]
    assert find_bill_payment(bill, pool) is None


def test_ignores_payment_outside_window():
    bill = BillCandidate("bill-1", "checking", 4500, datetime.date(2026, 7, 10))
    pool = [PaymentCandidate("p1", "checking", -4500, datetime.date(2026, 7, 25), "spend")]
    assert find_bill_payment(bill, pool, window_days=10) is None


def test_ignores_wrong_amount():
    bill = BillCandidate("bill-1", "checking", 4500, datetime.date(2026, 7, 10))
    pool = [PaymentCandidate("p1", "checking", -1000, datetime.date(2026, 7, 10), "spend")]
    assert find_bill_payment(bill, pool) is None


# --- F13: direction + one-bill-per-transaction guards -------------------------------------
#
# The old matcher compared abs(amount) alone and ignored `kind`, so any same-magnitude row near
# the due date could "pay" a bill — including money arriving. A silently-paid bill is worse than
# an unpaid one: the missing-bill alert never fires.


def test_a_same_magnitude_deposit_cannot_pay_a_bill():
    bill = BillCandidate("bill-1", "checking", 15000, datetime.date(2026, 7, 10))
    pool = [PaymentCandidate("dep", "checking", 15000, datetime.date(2026, 7, 10), "income")]
    assert find_bill_payment(bill, pool) is None


def test_a_refund_cannot_pay_a_bill():
    bill = BillCandidate("bill-1", "amex", 15000, datetime.date(2026, 7, 10))
    pool = [PaymentCandidate("ref", "amex", 15000, datetime.date(2026, 7, 10), "refund")]
    assert find_bill_payment(bill, pool) is None


def test_an_outflow_mislabelled_income_cannot_pay_a_bill():
    """Belt and braces: the kind guard holds even when the sign says outflow."""
    bill = BillCandidate("bill-1", "checking", 15000, datetime.date(2026, 7, 10))
    pool = [PaymentCandidate("odd", "checking", -15000, datetime.date(2026, 7, 10), "income")]
    assert find_bill_payment(bill, pool) is None


def test_a_transfer_leg_can_pay_a_bill():
    """Paying a card statement from checking is a transfer (CLAUDE.md 2), not a spend."""
    bill = BillCandidate("bill-1", "amex", 15000, datetime.date(2026, 7, 10))
    pool = [PaymentCandidate("pay", "amex", -15000, datetime.date(2026, 7, 11), "transfer")]
    match = find_bill_payment(bill, pool)
    assert match is not None and match.id == "pay"


def test_a_transaction_already_claimed_by_another_bill_is_excluded():
    """Two same-amount bills on one rail must not both point at the single payment."""
    bill = BillCandidate("bill-2", "checking", 4500, datetime.date(2026, 7, 10))
    pool = [PaymentCandidate("p1", "checking", -4500, datetime.date(2026, 7, 10), "spend")]
    assert find_bill_payment(bill, pool, exclude_transaction_ids=frozenset({"p1"})) is None
    # ...and the same pool still matches when nothing has claimed it.
    assert find_bill_payment(bill, pool) is not None


def test_the_closest_dated_unclaimed_payment_wins():
    bill = BillCandidate("bill-1", "checking", 4500, datetime.date(2026, 7, 10))
    pool = [
        PaymentCandidate("claimed", "checking", -4500, datetime.date(2026, 7, 10), "spend"),
        PaymentCandidate("free", "checking", -4500, datetime.date(2026, 7, 13), "spend"),
    ]
    match = find_bill_payment(bill, pool, exclude_transaction_ids=frozenset({"claimed"}))
    assert match is not None and match.id == "free"


def test_bill_missing_true_after_grace_window():
    assert is_bill_missing(datetime.date(2026, 7, 1), datetime.date(2026, 7, 10), grace_days=3)


def test_bill_missing_false_within_grace_window():
    assert not is_bill_missing(datetime.date(2026, 7, 1), datetime.date(2026, 7, 2), grace_days=3)


def test_should_alert_fires_only_on_rising_edge():
    assert should_alert(currently_true=True, previously_true=False)
    assert not should_alert(currently_true=True, previously_true=True)
    assert not should_alert(currently_true=False, previously_true=False)
    assert not should_alert(currently_true=False, previously_true=True)
