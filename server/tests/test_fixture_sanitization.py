"""Fixture-sanitization guard (ROADMAP #9 / V1 Tier 5 #39): the public-repo backstop behind manual
sanitization. gitleaks runs too but doesn't know what a real merchant or card number looks like;
this asserts every committed `.eml` fixture carries only sentinel values, so a real alert email
can never be committed by mistake (a PII leak already happened once this build).
"""

import re
from pathlib import Path

FIXTURES = sorted((Path(__file__).parent / "fixtures").glob("*.eml"))

# Card-ending / last-4 groups must be a sentinel: all the same digit (0000, 000000) or 9999.
_ENDING_RE = re.compile(r"ending(?:\s+in)?:?\s+(\d{4,})|last\s*4\s*#?:?\s*(\d{4})", re.IGNORECASE)
# A run of 13–19 digits is card-number-shaped — never legitimate in a sanitized fixture.
_LONG_NUMBER_RE = re.compile(r"\b\d{13,19}\b")
_TO_RE = re.compile(r"^To:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
_SAFE_RECIPIENT_DOMAINS = ("example.com", "example.org", ".invalid", "magpie.test")


def _sentinel_last4(digits: str) -> bool:
    tail = digits[-4:]
    return len(set(tail)) == 1 or tail == "9999"


def test_there_are_fixtures_to_check():
    assert FIXTURES, "no .eml fixtures found — the guard would pass vacuously"


def test_every_fixture_uses_only_sentinel_values():
    problems = []
    for path in FIXTURES:
        text = path.read_text(errors="replace")

        for m in _ENDING_RE.finditer(text):
            digits = m.group(1) or m.group(2)
            if not _sentinel_last4(digits):
                problems.append(f"{path.name}: non-sentinel card ending {digits!r}")

        if _LONG_NUMBER_RE.search(text):
            problems.append(f"{path.name}: contains a card-number-shaped digit run")

        for m in _TO_RE.finditer(text):
            recipient = m.group(1).lower()
            if not any(dom in recipient for dom in _SAFE_RECIPIENT_DOMAINS):
                problems.append(f"{path.name}: recipient not a sentinel domain: {recipient!r}")

    assert not problems, "un-sanitized fixture content:\n" + "\n".join(problems)
