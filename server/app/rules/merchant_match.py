"""Merchant normalization + matching (CLAUDE.md §5) — pure, no I/O. Card-network merchant
strings are noisy ("SQ *COFFEE SHOP #4021", "AMAZON MKTPLACE PMTS") — normalization strips
that noise down to a stable comparison key so a rule's `matcher` pattern can match reliably
across statement cycles.
"""

import re

# Card-network prefixes ("SQ *COFFEE", "TST* CAFE", "PAYPAL *THING", "POS DELI", "AMZN MKTP").
# F8: the separator after the prefix is MANDATORY — either a `*` (optionally spaced) or real
# whitespace. The old pattern made every separator optional, so it fired mid-word: SPOTIFY ->
# "OTIFY", POSTAL -> "TAL", POSTMATES -> "TMATES". Requiring a separator means the prefix only
# strips when it's genuinely a standalone token.
_NOISE_PREFIX_RE = re.compile(r"^(?:SQ|TST|PAYPAL|SP|POS|AMZN|WL)(?:\s*\*\s*|\s+)")
# Bank-statement transaction-type prefixes (from the real US Bank export): the actual merchant is
# what FOLLOWS. Stripping them turns "WEB AUTHORIZED PMT ROCKET MORTGAGE" into "ROCKET MORTGAGE"
# for display, better AI input, and rule matching — and it merges the same payee across
# transaction types (a "WEB AUTHORIZED PMT VENMO" and an "ELECTRONIC WITHDRAWAL VENMO" both
# become "VENMO"). Longest/most-specific alternatives first so "DEBIT PURCHASE -VISA" wins over
# "DEBIT PURCHASE". These are statement artifacts, not real merchant names, so stripping is safe.
_BANK_PREFIX_RE = re.compile(
    r"^(?:"
    r"WEB AUTHORIZED PMT|"
    r"RECURRING DEBIT PURCHASE|"
    r"DEBIT PURCHASE -VISA|"
    r"DEBIT PURCHASE|"
    r"ELECTRONIC WITHDRAWAL|"
    r"ELECTRONIC DEPOSIT|"
    r"ZELLE INSTANT PMT FROM|"
    r"ZELLE INSTANT PMT TO|"
    r"ACH WITHDRAWAL|"
    r"ACH DEPOSIT|"
    r"POS DEBIT"
    r")\s+"
)
_NON_ALNUM_RE = re.compile(r"[^A-Z0-9 ]")
_TRAILING_ID_RE = re.compile(r"\s+#?\d{3,}$")
_MULTISPACE_RE = re.compile(r"\s+")

# Peer-payment alerts carry a per-transaction confirmation reference *inside* the merchant string:
# "ZELLE INSTANT PMT TO Jose Handyman   USBLFdcrDsRt". The ref is unique to each payment, so every
# Zelle payment normalized to its own distinct merchant — 127 of them in the real ledger, when
# there are only 27 actual counterparties. A rule can therefore never match a Zelle payee: the
# string is never the same twice. `_TRAILING_ID_RE` misses these because it only matches digits.
#
# Stripping "any long trailing token" would be wrong, and not idempotent: it eats real surnames
# ("JOSE HANDYMAN" -> "JOSE"), corroding a name further on every re-normalization. The reference
# is recognizable instead by being long AND machine-shaped — a bank-code prefix, or containing a
# digit. A lone long surname ("PAPADOPOULOS") has neither, and the >= 2-token guard keeps the
# merchant from ever being emptied.
_REF_MIN_LEN = 10
_BANK_CODE = r"(?:USB|JPM|BOFA|WFB|CITI|PNC|TD)"
_PEER_REF_RE = re.compile(rf"^(?:{_BANK_CODE}[A-Z0-9]{{7,}}|[A-Z0-9]*\d[A-Z0-9]*)$")
_PEER_PREFIX_RE = re.compile(r"^ZELLE\s+INSTANT\s+PMT\s+(?:TO|FROM)\s+", re.IGNORECASE)


def _strip_peer_reference(text: str) -> str:
    tokens = text.split()
    if len(tokens) < 2:
        return text  # never leave the merchant empty
    last = tokens[-1]
    if len(last) < _REF_MIN_LEN or not _PEER_REF_RE.fullmatch(last):
        return text
    return " ".join(tokens[:-1])


def normalize_merchant(raw: str) -> str:
    text = raw.upper().strip()
    is_peer_payment = bool(_PEER_PREFIX_RE.match(text))
    text = _BANK_PREFIX_RE.sub("", text)  # strip the bank transaction-type wrapper first
    text = _NOISE_PREFIX_RE.sub("", text)  # then any card-network noise on the merchant itself
    text = _TRAILING_ID_RE.sub("", text)
    text = _NON_ALNUM_RE.sub(" ", text)
    text = _MULTISPACE_RE.sub(" ", text).strip()
    if is_peer_payment:
        # After the non-alnum pass, so a ref like "USB-Zj/ROn" is a single clean token by now.
        text = _strip_peer_reference(text)
    return text


def matches(matcher_pattern: str, merchant_norm: str) -> bool:
    """A rule's `matcher` is itself a normalized pattern (set at rule-creation time). Matching is
    **one-way** containment: the rule pattern must appear *within* the observed merchant, so a
    broad rule ("XCEL") matches a specific observed string ("XCEL ENERGY"), but a specific rule
    ("AMAZON PRIME") does NOT match a broader observed string ("AMAZON").

    F8: the previous two-way containment let a short observed merchant match a longer, unrelated
    rule — a plain "AMAZON" purchase mis-fired the "AMAZON PRIME" subscription rule. Rules are
    the broad patterns; the observed string is the specific instance they must be found inside."""
    if not matcher_pattern or not merchant_norm:
        return False
    pattern = normalize_merchant(matcher_pattern)
    observed = normalize_merchant(merchant_norm)
    if not pattern or not observed:
        return False
    return pattern in observed
