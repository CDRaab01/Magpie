"""Merchant normalization + matching (CLAUDE.md §5) — pure, no I/O. Card-network merchant
strings are noisy ("SQ *COFFEE SHOP #4021", "AMAZON MKTPLACE PMTS") — normalization strips
that noise down to a stable comparison key so a rule's `matcher` pattern can match reliably
across statement cycles.
"""

import re

_NOISE_PREFIX_RE = re.compile(r"^(SQ|TST|PAYPAL|SP|POS|AMZN|WL)\s*\*?\s*")
_NON_ALNUM_RE = re.compile(r"[^A-Z0-9 ]")
_TRAILING_ID_RE = re.compile(r"\s+#?\d{3,}$")
_MULTISPACE_RE = re.compile(r"\s+")


def normalize_merchant(raw: str) -> str:
    text = raw.upper().strip()
    text = _NOISE_PREFIX_RE.sub("", text)
    text = _TRAILING_ID_RE.sub("", text)
    text = _NON_ALNUM_RE.sub(" ", text)
    text = _MULTISPACE_RE.sub(" ", text).strip()
    return text


def matches(matcher_pattern: str, merchant_norm: str) -> bool:
    """A rule's `matcher` is itself a normalized pattern (set at rule-creation time); matching
    is substring containment either direction, so a broader pattern ("XCEL") matches a more
    specific observed string ("XCEL ENERGY") and vice versa."""
    if not matcher_pattern or not merchant_norm:
        return False
    pattern = normalize_merchant(matcher_pattern)
    observed = normalize_merchant(merchant_norm)
    return pattern in observed or observed in pattern
