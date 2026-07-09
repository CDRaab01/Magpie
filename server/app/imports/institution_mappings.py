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


# A positive (balance-reducing) amount on a card whose description looks like one of these is a
# PAYMENT from checking — a transfer, not income or a refund. Confirmed against Amex
# ("MOBILE PAYMENT - THANK YOU"); the markers are issuer-generic (Discover/US Bank use similar).
_CARD_PAYMENT_MARKERS = (
    "thank you",
    "mobile payment",
    "online payment",
    "autopay",
    "auto payment",
    "epayment",
    "e-payment",
)


def looks_like_card_payment(description: str | None) -> bool:
    if not description:
        return False
    d = description.lower()
    return any(m in d for m in _CARD_PAYMENT_MARKERS)


def default_kind_for(account_type: str, amount_cents: int, description: str | None) -> str:
    """Derive a transaction's kind from its (already sign-normalized) amount and account type.

    A depository account uses the plain sign convention: money in is income (a paycheck), money
    out is spend. But a CREDIT CARD never receives income — a positive (balance-reducing) amount
    is either a PAYMENT from checking (a transfer that nets to zero against the checking-side leg)
    or a merchant REFUND (negative spend in its original category, CLAUDE.md §2). Without this an
    Amex/Discover backfill books every card payment and refund as income — a household's single
    largest "income" would be paying off its own card. The cross-account transfer *pairing* still
    refines the checking-side leg separately (rule_service stage 1); this fixes the card side,
    which is what a card-only backfill needs to keep its rollups honest.
    """
    if amount_cents < 0:
        return "spend"
    if amount_cents > 0 and account_type == "card":
        return "transfer" if looks_like_card_payment(description) else "refund"
    return "income"
