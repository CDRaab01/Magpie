"""Generic CSV column detection + row parsing (CLAUDE.md Phase 3).

Deliberately institution-agnostic: no real Amex/Discover/US Bank sample exports were available
to build per-issuer parsers against (unlike Phase -1's email corpus, which collects real
samples before any parser is written). Instead this auto-detects common header aliases and
normalizes whatever's there — refine into dedicated per-institution parsers once real exports
exist to test against; don't guess at institution quirks without a real file in hand.

Pure — no I/O, no DB. Takes CSV text, returns normalized rows or raises CsvParseError.
"""

import csv
import io
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

DATE_HEADER_ALIASES = (
    "date",
    "transaction date",
    "posted date",
    "posting date",
    "trans date",
    "trans. date",  # Discover exports "Trans. Date" (with the period) — confirmed 2026-07-09
    "post date",  # Discover's second date column; "Trans. Date" wins by header order (first match)
)
AMOUNT_HEADER_ALIASES = ("amount", "transaction amount")
DEBIT_HEADER_ALIASES = ("debit", "withdrawal", "withdrawals", "payment")
CREDIT_HEADER_ALIASES = ("credit", "deposit", "deposits")
DESCRIPTION_HEADER_ALIASES = (
    "description",
    "merchant",
    "payee",
    "name",
    "transaction description",
)
BALANCE_HEADER_ALIASES = ("balance", "running balance", "account balance")

# Tried in order; the first one that parses the whole string wins.
DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d/%m/%Y", "%b %d, %Y", "%B %d, %Y")


@dataclass(frozen=True)
class ParsedCsvRow:
    date: date
    amount_cents: int  # signed — negative is an outflow, matching the ledger's convention
    description: str
    balance_cents: int | None


class CsvParseError(ValueError):
    pass


def _normalize_header(h: str) -> str:
    return h.strip().lower()


def _find_column(headers: list[str], aliases: tuple[str, ...]) -> str | None:
    for header in headers:
        if _normalize_header(header) in aliases:
            return header
    return None


def _parse_date(raw: str) -> date:
    raw = raw.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise CsvParseError(f"Unrecognized date format: {raw!r}")


_AMOUNT_STRIP_RE = re.compile(r"[^0-9.\-]")


def _parse_amount_cents(raw: str) -> int:
    """Signed integer cents from a currency string. Handles "$1,234.56", "(12.34)"
    (parenthetical negative — common for debits in bank/card exports), and a leading "-"."""
    raw = raw.strip()
    if not raw:
        raise CsvParseError("Empty amount")
    negative = False
    if raw.startswith("(") and raw.endswith(")"):
        negative = True
        raw = raw[1:-1]
    cleaned = _AMOUNT_STRIP_RE.sub("", raw)
    if cleaned.startswith("-"):
        negative = True
        cleaned = cleaned[1:]
    if not cleaned or cleaned == ".":
        raise CsvParseError(f"Unparseable amount: {raw!r}")
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        raise CsvParseError(f"Unparseable amount: {raw!r}")
    cents = int((value * 100).to_integral_value())
    return -cents if negative else cents


def parse_csv(text: str) -> list[ParsedCsvRow]:
    """Parse a CSV's full text content into normalized rows.

    A Date column and a Description column are required. The amount comes from either a
    single signed "Amount" column OR separate Debit/Credit columns (a Debit is always an
    outflow -> negative; a Credit an inflow -> positive) — a file is expected to use one
    convention consistently, not mix them row to row. A Balance column, if present, feeds
    `balance_cents` — the statement-checkpoint anchor (CLAUDE.md §2/§9).
    """
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise CsvParseError("Empty file or no header row")
    headers = list(reader.fieldnames)

    date_col = _find_column(headers, DATE_HEADER_ALIASES)
    desc_col = _find_column(headers, DESCRIPTION_HEADER_ALIASES)
    amount_col = _find_column(headers, AMOUNT_HEADER_ALIASES)
    debit_col = _find_column(headers, DEBIT_HEADER_ALIASES)
    credit_col = _find_column(headers, CREDIT_HEADER_ALIASES)
    balance_col = _find_column(headers, BALANCE_HEADER_ALIASES)

    if date_col is None:
        raise CsvParseError("No recognizable date column")
    if desc_col is None:
        raise CsvParseError("No recognizable description column")
    if amount_col is None and debit_col is None and credit_col is None:
        raise CsvParseError("No recognizable amount column (need Amount, or Debit/Credit)")

    rows: list[ParsedCsvRow] = []
    for line_no, raw_row in enumerate(reader, start=2):  # the header is line 1
        try:
            if amount_col is not None:
                amount_raw = (raw_row.get(amount_col) or "").strip()
                if not amount_raw:
                    continue  # blank trailing row — common in bank exports
                amount_cents = _parse_amount_cents(amount_raw)
            else:
                debit_raw = (raw_row.get(debit_col) or "").strip() if debit_col else ""
                credit_raw = (raw_row.get(credit_col) or "").strip() if credit_col else ""
                if debit_raw:
                    amount_cents = -abs(_parse_amount_cents(debit_raw))
                elif credit_raw:
                    amount_cents = abs(_parse_amount_cents(credit_raw))
                else:
                    continue  # both blank — blank trailing row

            row_date = _parse_date(raw_row[date_col])
            description = (raw_row.get(desc_col) or "").strip()

            balance_cents = None
            if balance_col is not None:
                balance_raw = (raw_row.get(balance_col) or "").strip()
                if balance_raw:
                    balance_cents = _parse_amount_cents(balance_raw)

            rows.append(
                ParsedCsvRow(
                    date=row_date,
                    amount_cents=amount_cents,
                    description=description,
                    balance_cents=balance_cents,
                )
            )
        except CsvParseError as e:
            raise CsvParseError(f"Line {line_no}: {e}") from e

    return rows
