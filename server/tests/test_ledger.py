import pytest

from app.ledger.classify import validate_kind_amount_sign, validate_transfer_pair
from app.ledger.rollups import (
    MonthlyRollup,
    TransactionForCategoryRollup,
    TransactionForRollup,
    rollup_by_category,
    rollup_month,
)

# --- validate_kind_amount_sign ------------------------------------------------------------

VALID_SIGN_CASES = [
    ("spend", -500),
    ("spend", -1),
    ("income", 500),
    ("income", 1),
    ("refund", 8000),
    ("refund", 1),
    ("transfer", -2400),
    ("transfer", 2400),
]


@pytest.mark.parametrize("kind,amount", VALID_SIGN_CASES)
def test_validate_kind_amount_sign_accepts_valid_combinations(kind, amount):
    validate_kind_amount_sign(kind, amount)  # must not raise


INVALID_SIGN_CASES = [
    ("spend", 500, "positive spend"),
    ("spend", 0, "zero spend"),
    ("income", -500, "negative income"),
    ("income", 0, "zero income"),
    ("refund", -500, "negative refund"),
    ("refund", 0, "zero refund"),
    ("transfer", 0, "zero transfer"),
]


@pytest.mark.parametrize("kind,amount,_label", INVALID_SIGN_CASES)
def test_validate_kind_amount_sign_rejects_invalid_combinations(kind, amount, _label):
    with pytest.raises(ValueError):
        validate_kind_amount_sign(kind, amount)


def test_validate_kind_amount_sign_rejects_unknown_kind():
    with pytest.raises(ValueError):
        validate_kind_amount_sign("bogus", -500)


# --- validate_transfer_pair ----------------------------------------------------------------


def test_validate_transfer_pair_accepts_a_true_zero_sum_pair():
    validate_transfer_pair(-24000, 24000)  # checking outflow, matching card-account inflow


def test_validate_transfer_pair_accepts_reversed_order():
    validate_transfer_pair(24000, -24000)


@pytest.mark.parametrize("a,b", [(-24000, 24001), (-24000, 23999), (-100, -100), (100, 100)])
def test_validate_transfer_pair_rejects_non_zero_sum(a, b):
    with pytest.raises(ValueError):
        validate_transfer_pair(a, b)


# --- rollup_month ----------------------------------------------------------------------


def test_rollup_month_empty_is_all_zero():
    assert rollup_month([]) == MonthlyRollup(0, 0, 0)


def test_rollup_month_income_only():
    txns = [TransactionForRollup("income", 200000)]
    assert rollup_month(txns) == MonthlyRollup(income_cents=200000, spend_cents=0, net_cents=200000)


def test_rollup_month_spend_only():
    txns = [TransactionForRollup("spend", -5000), TransactionForRollup("spend", -1200)]
    assert rollup_month(txns) == MonthlyRollup(income_cents=0, spend_cents=-6200, net_cents=-6200)


def test_rollup_month_refund_nets_spend_not_income():
    # $80 spent, $30 refunded on the same category -> net spend -$50, income untouched.
    txns = [TransactionForRollup("spend", -8000), TransactionForRollup("refund", 3000)]
    result = rollup_month(txns)
    assert result.income_cents == 0
    assert result.spend_cents == -5000
    assert result.net_cents == -5000


def test_rollup_month_transfer_excluded_entirely():
    # A card payment (checking outflow) and its matching card-account inflow must not move
    # income or spend at all — this is the double-count trap the whole design avoids.
    txns = [
        TransactionForRollup("income", 300000),
        TransactionForRollup("spend", -50000),
        TransactionForRollup("transfer", -24000),
        TransactionForRollup("transfer", 24000),
    ]
    result = rollup_month(txns)
    assert result.income_cents == 300000
    assert result.spend_cents == -50000
    assert result.net_cents == 250000


def test_rollup_month_mixed_realistic_month():
    txns = [
        TransactionForRollup("income", 450000),  # paycheck
        TransactionForRollup("spend", -120000),  # rent
        TransactionForRollup("spend", -8500),  # groceries
        TransactionForRollup("spend", -4200),  # dining
        TransactionForRollup("refund", 1500),  # partial return
        TransactionForRollup("transfer", -24000),  # checking -> card payment
        TransactionForRollup("transfer", 24000),  # card account receives payment
    ]
    result = rollup_month(txns)
    assert result.income_cents == 450000
    assert result.spend_cents == -120000 - 8500 - 4200 + 1500
    assert result.net_cents == result.income_cents + result.spend_cents


def test_rollup_month_rejects_unknown_kind():
    with pytest.raises(ValueError):
        rollup_month([TransactionForRollup("bogus", 100)])


# --- rollup_by_category --------------------------------------------------------------------


def test_rollup_by_category_groups_spend_by_category():
    txns = [
        TransactionForCategoryRollup("groceries", "spend", -8500),
        TransactionForCategoryRollup("groceries", "spend", -3200),
        TransactionForCategoryRollup("dining", "spend", -4200),
    ]
    totals = rollup_by_category(txns)
    assert totals == {"groceries": -8500 - 3200, "dining": -4200}


def test_rollup_by_category_nets_refund_into_its_category_not_income():
    txns = [
        TransactionForCategoryRollup("groceries", "spend", -8500),
        TransactionForCategoryRollup("groceries", "refund", 1500),
    ]
    totals = rollup_by_category(txns)
    assert totals == {"groceries": -8500 + 1500}


def test_rollup_by_category_excludes_transfers_and_income():
    txns = [
        TransactionForCategoryRollup("groceries", "spend", -8500),
        TransactionForCategoryRollup(None, "transfer", -24000),
        TransactionForCategoryRollup(None, "income", 450000),
    ]
    totals = rollup_by_category(txns)
    assert totals == {"groceries": -8500}


def test_rollup_by_category_rejects_unknown_kind():
    with pytest.raises(ValueError):
        rollup_by_category([TransactionForCategoryRollup("groceries", "bogus", 100)])
