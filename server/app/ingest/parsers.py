"""Per-issuer email parsers (CLAUDE.md Phase 4), built from the real corpus. Three issuers with
confirmed per-transaction email coverage (see ARCHITECTURE.md's status header):
  - Amex `AmericanExpress@welcome.americanexpress.com` — "Large Purchase Approved" (spend),
    "Merchant credit/refund" (refund).
  - US Bank `usbank@notifications.usbank.com` — "Your transaction is complete." (the account-wide
    debit/deposit alert, incl. paychecks) + Zelle payment alerts.
  - Discover `discover@services.discover.com` — "Transaction Alert" (spend). Confirmed emailing as
    of 2026-07-08; Phase -1 had found it push-only, so this coverage is new.

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
# "Date: July 06, 2026" — Discover's labeled date line (full month name, no weekday).
_LABELED_DATE_RE = re.compile(
    r"Date:\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.?\s+(\d{1,2}),?\s+(\d{4})",
    re.IGNORECASE,
)
# Discover's other labeled fields — clean key/value lines, so extract them precisely rather than
# by position ("Amount: $59.11" coexists with boilerplate like "a $1 authorization charge").
_LABELED_AMOUNT_RE = re.compile(r"Amount:\s*\$\s?([\d,]+\.\d{2})", re.IGNORECASE)
_LABELED_MERCHANT_RE = re.compile(r"Merchant:\s*(.+)")
_LABELED_LAST4_RE = re.compile(r"Last\s*4\s*#?:?\s*(\d{4})", re.IGNORECASE)

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
    m = _LABELED_DATE_RE.search(text)
    if m:
        month = _MONTHS[m.group(1).title()[:3]]
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
# The outbound counterparty on a "You sent..." alert ("...to Alex Sample.").
_ZELLE_TO_RE = re.compile(r"\bto ([A-Za-z][A-Za-z .'\-]+?)(?:\.|\s+on\b|\s+was\b|$)", re.IGNORECASE)

# Direction signals. F7: the old parser booked ANY Zelle "payment" subject as positive income,
# so an outbound "You sent a Zelle payment" would record money leaving as money arriving. The
# direction must be read explicitly from the body; an alert that matches neither shape (or, from
# an over-eager subject match, both) is unparsed rather than guessed.
_ZELLE_RECEIVED_SIGNALS = ("was deposited", "deposited in", "deposited into", "you received")
_ZELLE_SENT_SIGNALS = ("you sent", "was sent", "payment sent", "sent to")


def parse_usbank(subject: str, body: str) -> ParsedEmailEvent:
    """US Bank alerts, two real templates: the account-wide "Your transaction is complete." alert
    (ordinary debits + deposits/paychecks — the main coverage) and Zelle payment alerts in both
    directions (F7). Anything else, or an alert whose direction can't be read, is unparsed —
    never guessed, never assumed to be income."""
    subject_norm = subject.strip().lower()
    if "transaction is complete" in subject_norm:
        return _parse_usbank_transaction(body)
    if "zelle" in subject_norm and "payment" in subject_norm:
        return _parse_usbank_zelle(subject, body)
    raise UnparsedEmail(f"Unrecognized US Bank subject: {subject!r}")


def _parse_usbank_transaction(body: str) -> ParsedEmailEvent:
    """The "Your transaction is complete." alert. Direction is read from the wording: "Your
    transaction of $X" is a debit → spend; "Your deposit of $X" is money in → income (this is the
    paycheck path). No merchant is carried in this alert — CSV reconciliation fills that in."""
    amount = _amount_cents(body)
    if amount is None:
        raise UnparsedEmail("US Bank transaction alert matched subject but no dollar amount found")
    text = body.lower()
    if "deposit of" in text:
        kind, signed = "income", amount
    elif "transaction of" in text:
        kind, signed = "spend", -amount
    else:
        raise UnparsedEmail("US Bank transaction alert: could not tell a debit from a deposit")
    return ParsedEmailEvent(
        parser="usbank",
        parse_version="3",
        kind=kind,
        amount_cents=signed,
        merchant=None,
        event_date=_event_date(body),
        last4_hint=_last4(body),
    )


def _parse_usbank_zelle(subject: str, body: str) -> ParsedEmailEvent:
    """A received/deposited Zelle alert is income; a "you sent" alert is spend. Anything whose
    direction can't be read unambiguously is unparsed — never assumed to be income (F7)."""
    amount = _amount_cents(body)
    if amount is None:
        raise UnparsedEmail("US Bank Zelle email matched subject but no dollar amount found")

    text = f"{subject}\n{body}".lower()
    received = any(sig in text for sig in _ZELLE_RECEIVED_SIGNALS)
    sent = any(sig in text for sig in _ZELLE_SENT_SIGNALS)
    if received and not sent:
        kind, signed = "income", amount
        match = _ZELLE_FROM_RE.search(body)
    elif sent and not received:
        kind, signed = "spend", -amount
        match = _ZELLE_TO_RE.search(body)
    else:
        raise UnparsedEmail("US Bank Zelle email: could not determine payment direction")

    merchant = match.group(1).strip() if match else None
    return ParsedEmailEvent(
        parser="usbank",
        # v3: bumped alongside the "Your transaction is complete." template addition (v2 was the
        # F7 sent-vs-received direction guard); a replay can still distinguish by kind/version.
        parse_version="3",
        kind=kind,
        amount_cents=signed,
        merchant=merchant,
        event_date=_event_date(body),
        last4_hint=_last4(body),
    )


def parse_discover(subject: str, body: str) -> ParsedEmailEvent:
    """Discover's "Transaction Alert" — a per-transaction charge alert with clean labeled fields
    (Merchant:/Date:/Amount:/Last 4 #:). Discover is a credit card, so a transaction alert is a
    charge → spend. The amount is often a pending pre-authorization (the alert body says so); the
    posted amount is reconciled from CSV later, so this is captured as a pending spend."""
    if "transaction alert" not in subject.strip().lower():
        raise UnparsedEmail(f"Unrecognized Discover subject: {subject!r}")
    amount_match = _LABELED_AMOUNT_RE.search(body)
    if amount_match is None:
        raise UnparsedEmail("Discover transaction alert matched subject but no 'Amount:' line")
    amount = round(float(amount_match.group(1).replace(",", "")) * 100)
    merchant_match = _LABELED_MERCHANT_RE.search(body)
    last4_match = _LABELED_LAST4_RE.search(body)
    return ParsedEmailEvent(
        parser="discover",
        parse_version="1",
        kind="spend",
        amount_cents=-amount,
        merchant=merchant_match.group(1).strip() if merchant_match else None,
        event_date=_event_date(body),
        last4_hint=last4_match.group(1) if last4_match else None,
    )


# Keyed by the exact sender address a filter/poller sees — the same addresses the Phase -1
# Gmail filters already match on.
PARSERS_BY_SENDER = {
    "AmericanExpress@welcome.americanexpress.com": parse_amex,
    "usbank@notifications.usbank.com": parse_usbank,
    "discover@services.discover.com": parse_discover,
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
