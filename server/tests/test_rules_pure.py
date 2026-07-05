import datetime

import pytest

from app.rules.bands import is_within_band, median_cents
from app.rules.merchant_match import matches, normalize_merchant
from app.rules.recurrence import InvalidCadence, expected_next_date, is_within_cadence_window
from app.rules.transfer_matching import TransferCandidate, find_transfer_match

# --- recurrence -----------------------------------------------------------------------------


def test_weekly_cadence_next_date():
    assert expected_next_date(datetime.date(2026, 7, 1), {"kind": "weekly"}) == datetime.date(
        2026, 7, 8
    )


def test_monthly_cadence_clamps_short_months():
    # Jan 31 -> Feb has no 31st; clamp to the last valid day.
    assert expected_next_date(datetime.date(2026, 1, 31), {"kind": "monthly"}) == datetime.date(
        2026, 2, 28
    )


def test_monthly_cadence_normal_day():
    assert expected_next_date(datetime.date(2026, 6, 15), {"kind": "monthly"}) == datetime.date(
        2026, 7, 15
    )


def test_within_cadence_window_true_inside_slack():
    cadence = {"kind": "monthly", "slack_days": 5}
    assert is_within_cadence_window(datetime.date(2026, 6, 15), datetime.date(2026, 7, 18), cadence)


def test_within_cadence_window_false_outside_slack():
    cadence = {"kind": "monthly", "slack_days": 5}
    assert not is_within_cadence_window(
        datetime.date(2026, 6, 15), datetime.date(2026, 7, 25), cadence
    )


def test_unknown_cadence_kind_raises():
    with pytest.raises(InvalidCadence):
        expected_next_date(datetime.date(2026, 1, 1), {"kind": "yearly"})


# --- bands ----------------------------------------------------------------------------------


def test_median_cents_odd_count():
    assert median_cents([100, 300, 200]) == 200


def test_median_cents_even_count():
    assert median_cents([100, 200, 300, 400]) == 250


def test_median_cents_empty_raises():
    with pytest.raises(ValueError):
        median_cents([])


def test_within_band_true():
    # median of [3000, 3800] = 3400; 20% tolerance = 680; range [2720, 4080].
    assert is_within_band(3500, [3000, 3800], 0.2)


def test_within_band_false_too_high():
    assert not is_within_band(5000, [3000, 3800], 0.2)


def test_within_band_compares_magnitude_not_sign():
    # A -$35 bill against a $30/$38 spend history should read the same as +$35.
    assert is_within_band(-3500, [3000, 3800], 0.2)


# --- merchant_match ---------------------------------------------------------------------------


def test_normalize_strips_card_network_noise():
    assert normalize_merchant("SQ *COFFEE SHOP #4021") == "COFFEE SHOP"


def test_normalize_strips_trailing_transaction_id():
    assert normalize_merchant("XCEL ENERGY 88213091") == "XCEL ENERGY"


def test_matches_substring_either_direction():
    assert matches("XCEL", "XCEL ENERGY")
    assert matches("XCEL ENERGY", "XCEL")


def test_matches_false_for_unrelated_merchant():
    assert not matches("XCEL", "NETFLIX")


def test_matches_false_for_empty_inputs():
    assert not matches("", "XCEL")
    assert not matches("XCEL", "")


# --- transfer_matching ------------------------------------------------------------------------


def test_finds_exact_cancelling_pair_on_different_account():
    candidate = TransferCandidate("a", "checking", -5000, datetime.date(2026, 7, 5))
    pool = [
        TransferCandidate("b", "amex", 5000, datetime.date(2026, 7, 6)),
        TransferCandidate("c", "amex", 4999, datetime.date(2026, 7, 6)),  # doesn't cancel
    ]
    match = find_transfer_match(candidate, pool)
    assert match is not None
    assert match.id == "b"


def test_ignores_same_account_even_if_amount_cancels():
    candidate = TransferCandidate("a", "checking", -5000, datetime.date(2026, 7, 5))
    pool = [TransferCandidate("b", "checking", 5000, datetime.date(2026, 7, 5))]
    assert find_transfer_match(candidate, pool) is None


def test_ignores_matches_outside_the_date_window():
    candidate = TransferCandidate("a", "checking", -5000, datetime.date(2026, 7, 5))
    pool = [TransferCandidate("b", "amex", 5000, datetime.date(2026, 7, 20))]
    assert find_transfer_match(candidate, pool, window_days=3) is None


def test_picks_the_closest_dated_candidate_when_multiple_match():
    candidate = TransferCandidate("a", "checking", -5000, datetime.date(2026, 7, 5))
    pool = [
        TransferCandidate("far", "amex", 5000, datetime.date(2026, 7, 7)),
        TransferCandidate("near", "amex", 5000, datetime.date(2026, 7, 5)),
    ]
    match = find_transfer_match(candidate, pool)
    assert match.id == "near"
