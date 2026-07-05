from app.ledger.balances import (
    BalanceCheckpoint,
    TransactionForBalance,
    account_balance,
    balance_delta,
)


def test_account_balance_empty_is_zero():
    assert account_balance([]) == 0


def test_account_balance_sums_all_kinds_including_transfers():
    # Unlike the household rollup, an account's own balance includes its transfer legs —
    # money genuinely moved through this specific account.
    txns = [
        TransactionForBalance(200000),  # paycheck deposit
        TransactionForBalance(-50000),  # rent
        TransactionForBalance(-24000),  # checking -> card payment (a transfer leg)
    ]
    assert account_balance(txns) == 200000 - 50000 - 24000


def test_balance_delta_none_without_a_checkpoint():
    checkpoint = BalanceCheckpoint(computed_cents=125000, stated_cents=None)
    assert balance_delta(checkpoint) is None


def test_balance_delta_zero_when_reconciled():
    checkpoint = BalanceCheckpoint(computed_cents=125000, stated_cents=125000)
    assert balance_delta(checkpoint) == 0


def test_balance_delta_nonzero_flags_drift():
    checkpoint = BalanceCheckpoint(computed_cents=125000, stated_cents=124500)
    assert balance_delta(checkpoint) == 500
