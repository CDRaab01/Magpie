from datetime import date

from app.imports.pending_match import (
    PendingCandidate,
    find_pending_match,
    find_posted_duplicate,
)


def _c(id_, amount, d):
    return PendingCandidate(id_, amount, date.fromisoformat(d))


def test_exact_amount_and_date_matches():
    candidates = [_c("p", -4200, "2026-07-05")]
    match = find_pending_match(-4200, date(2026, 7, 5), candidates)
    assert match is not None and match.id == "p"


def test_no_candidates_is_none():
    assert find_pending_match(-4200, date(2026, 7, 5), []) is None


def test_tip_settlement_within_tolerance_matches():
    # Restaurant pre-auth alerted at $40.00, settled at $48.00 (20% tip) — same swipe.
    candidates = [_c("p", -4000, "2026-07-05")]
    match = find_pending_match(-4800, date(2026, 7, 6), candidates)
    assert match is not None and match.id == "p"


def test_amount_grown_beyond_tolerance_does_not_match():
    # $40 pre-auth vs a $60 posted charge (+50%) is not a tip — different swipe.
    candidates = [_c("p", -4000, "2026-07-05")]
    assert find_pending_match(-6000, date(2026, 7, 5), candidates) is None


def test_posted_smaller_than_pending_does_not_match():
    # A settlement lower than the pre-auth is the auth-hold-expiry domain, not reconciliation.
    candidates = [_c("p", -5000, "2026-07-05")]
    assert find_pending_match(-4000, date(2026, 7, 5), candidates) is None


def test_opposite_direction_never_matches():
    # A $42 spend can't reconcile a $42 deposit.
    candidates = [_c("p", 4200, "2026-07-05")]
    assert find_pending_match(-4200, date(2026, 7, 5), candidates) is None


def test_outside_date_window_does_not_match():
    candidates = [_c("p", -4200, "2026-07-01")]
    assert find_pending_match(-4200, date(2026, 7, 5), candidates, window_days=3) is None


def test_picks_closest_dated_then_smallest_amount_gap():
    candidates = [
        _c("far", -4200, "2026-07-08"),
        _c("near_exact", -4200, "2026-07-06"),
        _c("near_tipped", -4000, "2026-07-06"),
    ]
    match = find_pending_match(-4200, date(2026, 7, 5), candidates)
    # near_exact and near_tipped share the closest date; the exact amount wins the tiebreak.
    assert match.id == "near_exact"


# --- find_posted_duplicate: the replay path's inverse question (F15) ----------------------
#
# "Did the CSV backfill already post this swipe?" asked of a would-be pending email row. The
# tolerance is the same one above, seen from the other side: a posted row may be the same swipe
# at an equal or *tipped-up* magnitude, never a smaller one.


def test_posted_duplicate_matches_the_same_swipe_already_posted():
    posted = [_c("csv", -4200, "2026-07-05")]
    match = find_posted_duplicate(-4200, date(2026, 7, 5), posted)
    assert match is not None and match.id == "csv"


def test_posted_duplicate_matches_a_settled_tip():
    # The alert fired at the pre-tip $42; the CSV posted the $50 settlement.
    posted = [_c("csv", -5000, "2026-07-06")]
    assert find_posted_duplicate(-4200, date(2026, 7, 5), posted) is not None


def test_posted_row_smaller_than_the_alert_is_not_the_same_swipe():
    # A posted row *below* the alerted magnitude is the auth-hold domain, not a duplicate.
    posted = [_c("csv", -3000, "2026-07-05")]
    assert find_posted_duplicate(-4200, date(2026, 7, 5), posted) is None


def test_posted_duplicate_ignores_the_opposite_direction():
    posted = [_c("deposit", 4200, "2026-07-05")]
    assert find_posted_duplicate(-4200, date(2026, 7, 5), posted) is None


def test_posted_duplicate_ignores_rows_outside_the_window():
    posted = [_c("csv", -4200, "2026-07-20")]
    assert find_posted_duplicate(-4200, date(2026, 7, 5), posted) is None


def test_posted_duplicate_with_no_candidates_is_none():
    assert find_posted_duplicate(-4200, date(2026, 7, 5), []) is None


def test_posted_duplicate_prefers_the_closest_date():
    posted = [_c("far", -4200, "2026-07-07"), _c("near", -4200, "2026-07-05")]
    match = find_posted_duplicate(-4200, date(2026, 7, 5), posted)
    assert match.id == "near"
