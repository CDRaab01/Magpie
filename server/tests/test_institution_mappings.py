"""Per-institution sign conventions (F5)."""

from app.imports.institution_mappings import (
    default_kind_for,
    institution_flips_sign,
    looks_like_card_payment,
    looks_like_internal_transfer,
    resolve_sign_flip,
)


def test_amex_flips_sign():
    # Amex exports charges as positive — must flip to the ledger's negative=outflow convention.
    assert institution_flips_sign("American Express") is True
    assert institution_flips_sign("Amex") is True
    assert institution_flips_sign("amex gold") is True  # substring match on free-text institution
    assert institution_flips_sign("Discover") is True  # confirmed positive-is-charge 2026-07-09


def test_depository_and_unknown_default_to_no_flip():
    assert institution_flips_sign("US Bank") is False
    assert institution_flips_sign("Some Credit Union") is False
    assert institution_flips_sign("") is False


def test_explicit_override_wins_over_institution_default():
    # A future import-dialog checkbox can force either way regardless of the institution default.
    assert resolve_sign_flip("US Bank", override=True) is True
    assert resolve_sign_flip("American Express", override=False) is False
    # None override falls back to the institution default.
    assert resolve_sign_flip("American Express", override=None) is True
    assert resolve_sign_flip("US Bank", override=None) is False


# --- card-aware kind derivation (the backfill fix: a card never has income) ------------------


def test_card_positive_amount_is_never_income():
    # After the Amex sign flip, a charge is negative (spend) and a credit is positive. On a card a
    # positive amount is a payment (transfer) or a refund — NEVER income.
    assert default_kind_for("card", -4500, "MEIJER STORE") == "spend"
    assert default_kind_for("card", 16683, "MOBILE PAYMENT - THANK YOU") == "transfer"
    assert default_kind_for("card", 106, "AMAZON MARKETPLACE REFUND") == "refund"


def test_depository_keeps_plain_income_spend():
    # A checking account DOES receive income (paychecks); the card rule must not touch it.
    assert default_kind_for("depository", 450000, "EMPLOYER PAYROLL") == "income"
    assert default_kind_for("depository", -12000, "XCEL ENERGY") == "spend"


def test_card_payment_markers():
    assert looks_like_card_payment("MOBILE PAYMENT - THANK YOU") is True
    assert looks_like_card_payment("AUTOPAY PAYMENT") is True
    assert looks_like_card_payment("ONLINE PAYMENT THANK YOU") is True
    assert looks_like_card_payment("AMAZON MARKETPLACE") is False
    assert looks_like_card_payment(None) is False


def test_internal_transfer_between_own_depository_accounts_is_a_transfer():
    # Confirmed against the real US Bank export — a checking<->savings move is neither income nor
    # spend on either side, and depository<->depository can't auto-pair, so detect by description.
    assert looks_like_internal_transfer("MOBILE BANKING TRANSFER WITHDRAWAL 6340") is True
    assert looks_like_internal_transfer("MOBILE BANKING TRANSFER DEPOSIT 7197") is True
    assert looks_like_internal_transfer("TELEPHONE TRANSFER 7197") is True  # phone-initiated variant
    assert looks_like_internal_transfer("ELECTRONIC DEPOSIT BAE SYSTEMS") is False
    # Applies on either sign / account type (transfer allows any sign).
    assert (
        default_kind_for("depository", -500000, "MOBILE BANKING TRANSFER WITHDRAWAL 6340")
        == "transfer"
    )
    assert (
        default_kind_for("depository", 500000, "MOBILE BANKING TRANSFER DEPOSIT 7197") == "transfer"
    )
    # A real paycheck deposit is still income, not swept up by the transfer rule.
    assert default_kind_for("depository", 414574, "ELECTRONIC DEPOSIT BAE SYSTEMS") == "income"
