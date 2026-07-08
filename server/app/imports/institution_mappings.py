"""Per-institution CSV conventions (F5 / V1.md #13).

`csv_parser` normalizes columns and signs by the *file's own* convention (negative = outflow).
But card issuers disagree on sign: **Amex exports a charge as a POSITIVE amount**, so importing an
Amex history through the generic parser books every charge as income (and every payment as spend)
— the whole backfill inverted. This maps an institution to whether its amounts need a full sign
flip to reach the ledger's "negative = outflow" convention.

Discipline (Phase -1 rule): only conventions confirmed against a real export — or notorious enough
to be safe, like Amex — belong here. An unknown institution defaults to **no flip** (the standard
signed convention, correct for depository/checking exports). A card issuer we haven't validated a
real file for (e.g. **Discover** — almost certainly positive-is-charge too, but unconfirmed) is
left out deliberately; add it once a real CSV proves it, or pass an explicit override at import.
"""

# Substrings that mark an issuer whose CSV uses "positive amount = a charge/outflow", so every
# row's sign must be flipped. Substring (not exact) match so "Amex Gold", "American Express Card",
# etc. all resolve. Keep this list to confirmed conventions only.
_POSITIVE_IS_CHARGE_ALIASES = ("amex", "american express")


def _normalize(institution: str) -> str:
    return institution.strip().lower()


def institution_flips_sign(institution: str) -> bool:
    """The known default sign-flip for an institution (F5). Amex exports charges as positive;
    unknown institutions default to no flip."""
    norm = _normalize(institution)
    return any(alias in norm for alias in _POSITIVE_IS_CHARGE_ALIASES)


def resolve_sign_flip(institution: str, override: bool | None = None) -> bool:
    """Whether to flip every row's sign for this import. An explicit per-import override wins
    (the future import-dialog checkbox); otherwise the institution's known default applies."""
    if override is not None:
        return override
    return institution_flips_sign(institution)
