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
