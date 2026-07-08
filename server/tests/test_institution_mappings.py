"""Per-institution sign conventions (F5)."""

from app.imports.institution_mappings import institution_flips_sign, resolve_sign_flip


def test_amex_flips_sign():
    # Amex exports charges as positive — must flip to the ledger's negative=outflow convention.
    assert institution_flips_sign("American Express") is True
    assert institution_flips_sign("Amex") is True
    assert institution_flips_sign("amex gold") is True  # substring match on free-text institution


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
