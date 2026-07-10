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
    assert normalize_merchant("PAYPAL *SOME STORE") == "SOME STORE"
    assert normalize_merchant("POS DELI MART") == "DELI MART"


def test_normalize_strips_trailing_transaction_id():
    assert normalize_merchant("XCEL ENERGY 88213091") == "XCEL ENERGY"


def test_normalize_strips_bank_statement_prefixes():
    # Real US Bank descriptions wrap the merchant in a transaction-type prefix.
    assert normalize_merchant("WEB AUTHORIZED PMT ROCKET MORTGAGE") == "ROCKET MORTGAGE"
    assert normalize_merchant("ELECTRONIC WITHDRAWAL PROFED FED CU") == "PROFED FED CU"
    assert normalize_merchant("RECURRING DEBIT PURCHASE FRONTIER COMM") == "FRONTIER COMM"
    assert normalize_merchant("ELECTRONIC DEPOSIT BAE SYSTEMS") == "BAE SYSTEMS"
    # "DEBIT PURCHASE -VISA" must win over the shorter "DEBIT PURCHASE", and card-network noise
    # on the inner merchant still strips.
    assert normalize_merchant("DEBIT PURCHASE -VISA COSTCO WHSE") == "COSTCO WHSE"
    assert normalize_merchant("DEBIT PURCHASE COSTCO WHSE") == "COSTCO WHSE"
    # Same payee across transaction types collapses to one merchant.
    assert normalize_merchant("WEB AUTHORIZED PMT VENMO") == "VENMO"
    assert normalize_merchant("ELECTRONIC WITHDRAWAL VENMO") == "VENMO"


def test_normalize_leaves_ordinary_merchants_untouched():
    # A real merchant that merely starts with a word like "ELECTRONIC" isn't a bank prefix (no
    # following transaction-type phrase), so nothing is stripped.
    assert normalize_merchant("ELECTRONIC ARTS") == "ELECTRONIC ARTS"
    assert normalize_merchant("MEIJER STORE") == "MEIJER STORE"


def test_f8_noise_prefix_does_not_fire_mid_word():
    # The old all-optional-separator regex chewed the front off real merchant names.
    assert normalize_merchant("SPOTIFY") == "SPOTIFY"  # not "OTIFY" (SP)
    assert normalize_merchant("POSTAL SERVICE") == "POSTAL SERVICE"  # not "TAL SERVICE" (POS)
    assert normalize_merchant("POSTMATES") == "POSTMATES"  # not "TMATES" (POS)
    assert normalize_merchant("SQUARESPACE") == "SQUARESPACE"  # not "UARESPACE" (SQ)


def test_matches_one_way_pattern_within_observed():
    # A broad rule pattern matches a specific observed merchant...
    assert matches("XCEL", "XCEL ENERGY")


def test_f8_specific_rule_does_not_match_broader_observed():
    # ...but a specific rule must NOT fire on a broader/shorter observed merchant (the AMAZON
    # PRIME subscription rule must not swallow every plain AMAZON purchase).
    assert not matches("AMAZON PRIME", "AMAZON")
    assert matches("AMAZON", "AMAZON PRIME")  # the reverse is the intended broad match


def test_matches_false_for_unrelated_merchant():
    assert not matches("XCEL", "NETFLIX")


def test_matches_false_for_empty_inputs():
    assert not matches("", "XCEL")
    assert not matches("XCEL", "")


# --- transfer_matching ------------------------------------------------------------------------


def _checking(id_, amount, d, review_state="needs_review"):
    return TransferCandidate(id_, "checking", "depository", amount, d, review_state)


def _card(id_, amount, d, review_state="needs_review"):
    return TransferCandidate(id_, "amex", "card", amount, d, review_state)


def test_finds_card_payment_pair_outflow_from_checking_inflow_to_card():
    candidate = _checking("a", -5000, datetime.date(2026, 7, 5))  # checking outflow
    pool = [
        _card("b", 5000, datetime.date(2026, 7, 6)),  # card payment inflow — the pair
        _card("c", 4999, datetime.date(2026, 7, 6)),  # doesn't cancel
    ]
    match = find_transfer_match(candidate, pool)
    assert match is not None
    assert match.id == "b"


def test_ignores_same_account_even_if_amount_cancels():
    candidate = _checking("a", -5000, datetime.date(2026, 7, 5))
    pool = [_checking("b", 5000, datetime.date(2026, 7, 5))]
    assert find_transfer_match(candidate, pool) is None


def test_ignores_matches_outside_the_date_window():
    candidate = _checking("a", -5000, datetime.date(2026, 7, 5))
    pool = [_card("b", 5000, datetime.date(2026, 7, 20))]
    assert find_transfer_match(candidate, pool, window_days=3) is None


def test_picks_the_closest_dated_candidate_when_multiple_match():
    candidate = _checking("a", -5000, datetime.date(2026, 7, 5))
    pool = [
        _card("far", 5000, datetime.date(2026, 7, 7)),
        _card("near", 5000, datetime.date(2026, 7, 5)),
    ]
    match = find_transfer_match(candidate, pool)
    assert match.id == "near"


def test_f3_card_spend_and_coincidental_deposit_are_not_a_transfer():
    # The canonical F3 false positive: a $50 card SPEND (card leg negative) and an unrelated
    # $50 Zelle DEPOSIT into checking (depository leg positive). Amounts cancel and accounts
    # differ, but it is NOT payment-shaped — the card leg must be the positive inflow.
    card_spend = _card("spend", -5000, datetime.date(2026, 7, 5))
    checking_deposit = _checking("zelle", 5000, datetime.date(2026, 7, 5))
    assert find_transfer_match(card_spend, [checking_deposit]) is None
    # ...and symmetrically, from the deposit's point of view.
    assert find_transfer_match(checking_deposit, [card_spend]) is None


def test_f3_two_depository_accounts_do_not_pair():
    # Internal checking<->savings movement has no card leg; v1 leaves it for review rather
    # than risk a false pair (CLAUDE.md §2: card payments are the transfer shape).
    savings = TransferCandidate("s", "savings", "depository", 5000, datetime.date(2026, 7, 5))
    checking = _checking("c", -5000, datetime.date(2026, 7, 5))
    assert find_transfer_match(checking, [savings]) is None


# --- The pairing window (widened 3 -> 5 on 2026-07-10) -----------------------------------
#
# The real Amex backfill missed a pair by exactly one day, leaving $8,000 booked as spend.


def test_legs_four_days_apart_pair_the_real_amex_case():
    """Amex credited the $8,000 payment on the 6th; checking cleared it on the 10th."""
    checking = _checking("chk", -800000, datetime.date(2025, 2, 10))
    pool = [_card("amex", 800000, datetime.date(2025, 2, 6))]
    match = find_transfer_match(checking, pool)
    assert match is not None and match.id == "amex"


def test_legs_five_days_apart_still_pair():
    checking = _checking("chk", -800000, datetime.date(2025, 2, 11))
    pool = [_card("amex", 800000, datetime.date(2025, 2, 6))]
    assert find_transfer_match(checking, pool) is not None


def test_legs_six_days_apart_do_not_pair():
    """The window is widened, not removed."""
    checking = _checking("chk", -800000, datetime.date(2025, 2, 12))
    pool = [_card("amex", 800000, datetime.date(2025, 2, 6))]
    assert find_transfer_match(checking, pool) is None


def test_widened_window_still_refuses_a_non_payment_shape():
    """F3 holds: a wider window must not fuse a coincidental same-amount deposit."""
    card_spend = _card("spend", -5000, datetime.date(2026, 7, 10))
    pool = [_checking("deposit", 5000, datetime.date(2026, 7, 14))]
    assert find_transfer_match(card_spend, pool) is None


# --- Peer-payment confirmation references (added 2026-07-10) ------------------------------
#
# Zelle puts a per-transaction reference inside the merchant string, so every payment to the
# same person normalized to a different merchant (127 "merchants" for 27 real counterparties in
# the live ledger) and no rule could ever match one.


def test_zelle_reference_is_stripped_leaving_the_counterparty():
    assert (
        normalize_merchant("ZELLE INSTANT PMT TO Jose Handyman   USBLFdcrDsRt") == "JOSE HANDYMAN"
    )
    assert normalize_merchant("ZELLE INSTANT PMT FROM AARON S WILLIAMS JPM99AK69Y2V") == (
        "AARON S WILLIAMS"
    )


def test_a_long_digit_laden_reference_is_stripped():
    raw = "ZELLE INSTANT PMT TO Fence 20250621042000013P1BP2PUSBZjROnGFZQ"
    assert normalize_merchant(raw) == "FENCE"


def test_every_payment_to_one_person_normalizes_to_the_same_merchant():
    """The whole point: a rule can only match if the string is stable across payments."""
    a = normalize_merchant("ZELLE INSTANT PMT TO Jose Handyman   USBLFdcrDsRt")
    b = normalize_merchant("ZELLE INSTANT PMT TO Jose Handyman   USBDT9vo4fxH")
    assert a == b == "JOSE HANDYMAN"


def test_normalization_is_idempotent_and_never_eats_a_surname():
    """A naive 'strip any long trailing token' rule turns JOSE HANDYMAN into JOSE, and would
    shorten the name again on every re-normalization pass."""
    for name in ("JOSE HANDYMAN", "AARON S WILLIAMS", "BETSY GARDENER", "PAPADOPOULOS"):
        assert normalize_merchant(name) == name
        assert normalize_merchant(normalize_merchant(name)) == name


def test_a_store_number_is_stripped_by_the_pre_existing_rule_not_the_peer_rule():
    """Trailing store numbers were already stripped (that is what merges "STORE 138" across
    cycles); the peer-ref rule must not change this behavior for ordinary merchants."""
    assert normalize_merchant("MEIJER STORE 138") == "MEIJER STORE"
    assert normalize_merchant("MEIJER STORE 12") == "MEIJER STORE 12"  # < 3 digits: kept


def test_a_non_peer_merchant_keeps_a_long_trailing_token():
    """The ref strip is scoped to peer payments; an ordinary merchant is not second-guessed."""
    assert normalize_merchant("HALLERCOLVIN PC HALLERCOLVININ") == "HALLERCOLVIN PC HALLERCOLVININ"


def test_bank_prefixes_still_strip():
    assert normalize_merchant("WEB AUTHORIZED PMT VENMO") == "VENMO"
    assert normalize_merchant("ELECTRONIC WITHDRAWAL GEICO") == "GEICO"
