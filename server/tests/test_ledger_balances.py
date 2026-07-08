from datetime import date

from app.ledger.balances import (
    CheckpointAnchor,
    DatedAmount,
    derived_balance,
    reconciliation_delta,
)


def _txn(d: str, amount: int) -> DatedAmount:
    return DatedAmount(date=date.fromisoformat(d), amount=amount)


# --- derived_balance -----------------------------------------------------------------------


def test_derived_balance_empty_is_zero():
    assert derived_balance([]) == 0


def test_derived_balance_without_anchor_sums_all_kinds_including_transfers():
    # Unlike the household rollup, an account's own balance includes its transfer legs —
    # money genuinely moved through this specific account. No checkpoint ⇒ plain signed sum.
    txns = [
        _txn("2026-07-01", 200000),  # paycheck deposit
        _txn("2026-07-02", -50000),  # rent
        _txn("2026-07-03", -24000),  # checking -> card payment (a transfer leg)
    ]
    assert derived_balance(txns) == 200000 - 50000 - 24000


def test_derived_balance_anchors_at_earliest_checkpoint():
    # The anchor's stated balance already includes everything on/before its date; only
    # transactions strictly after it accrue on top.
    anchor = CheckpointAnchor(statement_date=date(2026, 6, 30), stated_cents=100000)
    txns = [
        _txn("2026-06-15", -9999),  # before the anchor — baked into stated, must be ignored
        _txn("2026-06-30", -1),  # on the anchor date — also already in the stated balance
        _txn("2026-07-05", 25000),  # after the anchor — accrues
        _txn("2026-07-10", -4000),  # after the anchor — accrues
    ]
    assert derived_balance(txns, anchor=anchor) == 100000 + 25000 - 4000


# --- reconciliation_delta (the honesty meter) ----------------------------------------------


def test_reconciliation_delta_none_without_a_checkpoint():
    assert reconciliation_delta([], None, None) is None


def test_reconciliation_delta_single_checkpoint_reconciles_to_zero():
    # One checkpoint anchors the account; there's nothing between two points to check, so the
    # delta is trivially zero regardless of what the ledger holds.
    cp = CheckpointAnchor(statement_date=date(2026, 7, 2), stated_cents=98350)
    txns = [_txn("2026-07-01", -450), _txn("2026-07-02", -1200)]
    assert reconciliation_delta(txns, cp, cp) == 0


def test_reconciliation_delta_zero_when_window_fully_accounts_for_movement():
    # The F1 invariant: backfill an account with UNKNOWN prior history — the first checkpoint
    # is the only truth about the starting balance — and it still reconciles to zero, because
    # transactions before the earliest checkpoint are never summed.
    earliest = CheckpointAnchor(statement_date=date(2026, 5, 31), stated_cents=100000)
    latest = CheckpointAnchor(statement_date=date(2026, 6, 30), stated_cents=120000)
    txns = [
        _txn("2026-04-10", -777777),  # ancient history we never saw — must be ignored
        _txn("2026-05-31", 5),  # on the earliest date — baked into its stated balance
        _txn("2026-06-05", 30000),  # in the window
        _txn("2026-06-20", -10000),  # in the window  (net window movement = +20000)
        _txn("2026-07-01", 999),  # after the latest checkpoint — not part of this delta
    ]
    # 100000 + (30000 - 10000) - 120000 == 0
    assert reconciliation_delta(txns, earliest, latest) == 0


def test_reconciliation_delta_flags_a_gap_in_the_ledger():
    # A missing transaction between two checkpoints shows up as a nonzero delta — the point of
    # the honesty meter.
    earliest = CheckpointAnchor(statement_date=date(2026, 5, 31), stated_cents=100000)
    latest = CheckpointAnchor(statement_date=date(2026, 6, 30), stated_cents=120000)
    txns = [_txn("2026-06-05", 30000)]  # missing the -10000 row ⇒ ledger over-states by 10000
    # 100000 + 30000 - 120000 == 10000
    assert reconciliation_delta(txns, earliest, latest) == 10000
