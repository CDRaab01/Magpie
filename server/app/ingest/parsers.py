"""Per-issuer email parsers (CLAUDE.md Phase 4), built from the real Phase -1 corpus —
Amex `AmericanExpress@welcome.americanexpress.com` and US Bank
`usbank@notifications.usbank.com` are the only two issuers with confirmed real per-transaction
alert coverage (see ARCHITECTURE.md's status header). Discover's alerts are, per the account's
own preferences, pushed rather than emailed — no Discover parser exists here because there is
no real sample to build one against; guessing at a format would violate the entire point of
Phase -1.

Pure — no I/O, no DB. Each parser takes a subject + plaintext body and returns a
`ParsedEmailEvent`, or raises `UnparsedEmail` if the template isn't recognized. An unparsed
result is not a bug: CLAUDE.md's own design treats a silently-unrecognized email as the
pipeline's worst failure mode, and building a visible "unparsed" outcome (not a crash, not a
best-effort guess) is the intended safety net for exactly the templates these regexes don't
yet cover.
"""

import re
from dataclasses import dataclass
from datetime import date

# spend < 0, income/refund > 0 — same sign convention as app/ledger/classify.py.
EVENT_KINDS = ("spend", "income", "refund")


@dataclass(frozen=True)
class ParsedEmailEvent:
    parser: str  # "amex" | "usbank" — matches IngestEvent.parser
    parse_version: str
    kind: str  # "spend" | "income" | "refund"
    amount_cents: int  # signed, per EVENT_KINDS
    merchant: str | None
    event_date: date | None
    last4_hint: str | None


class UnparsedEmail(ValueError):
    """Raised when a recognized sender's email doesn't match any known subject/body template."""


_AMOUNT_RE = re.compile(r"\$\s?([\d,]+\.\d{2})")
_ENDING_RE = re.compile(r"ending(?:\s+in)?:?\s+(\d{4,})", re.IGNORECASE)
# "Sun, Jul 5, 2026" / "Jul 5, 2026" style — Amex's purchase-alert date line.
_LONG_DATE_RE = re.compile(
    r"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),?\s+"
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.?\s+(\d{1,2}),?\s+(\d{4})\b"
)
# "Received date: 07/02/2026" — US Bank's alert date line.
_SLASH_DATE_RE = re.compile(r"Received date:\s*(\d{1,2})/(\d{1,2})/(\d{4})", re.IGNORECASE)

_MONTHS = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}


def _last_amount_match(text: str) -> re.Match | None:
    """The LAST dollar figure in the body, not the first: Amex's boilerplate ("...was more
    than $1.00") states the alert *threshold* before the real charged amount ever appears."""
    matches = list(_AMOUNT_RE.finditer(text))
    return matches[-1] if matches else None


def _amount_cents(text: str) -> int | None:
    m = _last_amount_match(text)
    if not m:
        return None
    return round(float(m.group(1).replace(",", "")) * 100)


def _last4(text: str) -> str | None:
    m = _ENDING_RE.search(text)
    if not m:
        return None
    return m.group(1)[-4:]


def _event_date(text: str) -> date | None:
    m = _SLASH_DATE_RE.search(text)
    if m:
        month, day, year = (int(g) for g in m.groups())
        return date(year, month, day)
    m = _LONG_DATE_RE.search(text)
    if m:
        month = _MONTHS[m.group(1)[:3]]
        return date(int(m.group(3)), month, int(m.group(2)))
    return None


def _merchant_before_amount(text: str) -> str | None:
    """The line (or trailing clause) immediately before the real charged amount — Amex's
    templates put the merchant name directly above/before it."""
    m = _last_amount_match(text)
    if not m:
        return None
    before = text[: m.start()]
    # Take the last non-empty line/clause, splitting on newlines first (multi-line HTML-derived
    # text) and falling back to sentence-ish punctuation for single-line flattened text.
    for candidate in reversed(before.splitlines()):
        # Strip trailing separator punctuation ("-", ":") a signed amount often leaves behind
        # (e.g. "...ONLINE -" before "-$18.00") — otherwise it kills the word-walk below on its
        # very first (non-alphabetic) iteration.
        candidate = candidate.strip().rstrip("-:").strip()
        if candidate:
            # Flattened single-line bodies run several sentences together; take the trailing
            # run of Title Case / ALL CAPS words as the merchant token.
            words = candidate.split()
            tail: list[str] = []
            for word in reversed(words):
                bare = word.strip("-:,.")
                if bare and (bare[:1].isupper() or bare.isupper()):
                    tail.insert(0, word)
                else:
                    break
            merchant = " ".join(tail).strip()
            return merchant or candidate
    return None


def parse_amex(subject: str, body: str) -> ParsedEmailEvent:
    """Two known real templates: a large-purchase alert (spend) and a merchant credit/refund
    notice (refund). Both carry merchant + amount + (usually) a card-ending hint."""
    subject_norm = subject.strip().lower()
    if "large purchase" in subject_norm:
        kind = "spend"
    elif "merchant credit" in subject_norm or "refund" in subject_norm:
        kind = "refund"
    else:
        raise UnparsedEmail(f"Unrecognized Amex subject: {subject!r}")

    amount = _amount_cents(body)
    if amount is None:
        raise UnparsedEmail("Amex email matched a known subject but no dollar amount found")

    signed = -amount if kind == "spend" else amount
    return ParsedEmailEvent(
        parser="amex",
        parse_version="1",
        kind=kind,
        amount_cents=signed,
        merchant=_merchant_before_amount(body),
        event_date=_event_date(body),
        last4_hint=_last4(body),
    )


_ZELLE_FROM_RE = re.compile(
    r"(?:payment of \$[\d,]+\.\d{2}\s+)?from ([A-Za-z][A-Za-z .'\-]+?) was deposited",
    re.IGNORECASE,
)


def parse_usbank(subject: str, body: str) -> ParsedEmailEvent:
    """One known real template family: a Zelle payment-received alert (income/deposit)."""
    subject_norm = subject.strip().lower()
    if "zelle" not in subject_norm or "payment" not in subject_norm:
        raise UnparsedEmail(f"Unrecognized US Bank subject: {subject!r}")

    amount = _amount_cents(body)
    if amount is None:
        raise UnparsedEmail("US Bank Zelle email matched subject but no dollar amount found")

    counterparty_match = _ZELLE_FROM_RE.search(body)
    merchant = counterparty_match.group(1).strip() if counterparty_match else None

    return ParsedEmailEvent(
        parser="usbank",
        parse_version="1",
        kind="income",
        amount_cents=amount,
        merchant=merchant,
        event_date=_event_date(body),
        last4_hint=_last4(body),
    )


# Keyed by the exact sender address a filter/poller sees — the same addresses the Phase -1
# Gmail filters already match on.
PARSERS_BY_SENDER = {
    "AmericanExpress@welcome.americanexpress.com": parse_amex,
    "usbank@notifications.usbank.com": parse_usbank,
}


def parse_email(sender: str, subject: str, body: str) -> ParsedEmailEvent:
    """Dispatch to the right per-issuer parser by exact sender address.

    A sender address ingestion has never seen at all (not just an unrecognized subject) is a
    parser gap, not a content gap — still surfaced as UnparsedEmail either way, but callers can
    distinguish via `parser` being unresolvable if they need to (e.g. to flag "brand-new sender,
    might need a template" versus "known issuer, new subject/format").
    """
    parser = PARSERS_BY_SENDER.get(sender)
    if parser is None:
        raise UnparsedEmail(f"No parser registered for sender: {sender!r}")
    return parser(subject, body)
