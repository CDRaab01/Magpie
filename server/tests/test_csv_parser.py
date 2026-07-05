import datetime

import pytest

from app.imports.csv_parser import CsvParseError, ParsedCsvRow, parse_csv

# --- happy paths: header alias variety -----------------------------------------------------


def test_standard_amount_column():
    text = "Date,Description,Amount\n2026-07-01,Coffee Shop,-4.50\n2026-07-02,Paycheck,1500.00\n"
    rows = parse_csv(text)
    assert rows == [
        ParsedCsvRow(datetime.date(2026, 7, 1), -450, "Coffee Shop", None),
        ParsedCsvRow(datetime.date(2026, 7, 2), 150000, "Paycheck", None),
    ]


def test_alternate_header_names():
    text = "Transaction Date,Merchant,Transaction Amount\n07/01/2026,Coffee Shop,-4.50\n"
    rows = parse_csv(text)
    assert rows == [ParsedCsvRow(datetime.date(2026, 7, 1), -450, "Coffee Shop", None)]


def test_case_insensitive_headers():
    text = "DATE,description,AMOUNT\n2026-07-01,Coffee,-4.50\n"
    rows = parse_csv(text)
    assert len(rows) == 1


def test_debit_credit_columns():
    text = "Date,Description,Debit,Credit\n2026-07-01,Coffee Shop,4.50,\n2026-07-02,Paycheck,,1500.00\n"
    rows = parse_csv(text)
    assert rows[0].amount_cents == -450
    assert rows[1].amount_cents == 150000


def test_balance_column_optional_but_captured_when_present():
    text = "Date,Description,Amount,Balance\n2026-07-01,Coffee,-4.50,995.50\n"
    rows = parse_csv(text)
    assert rows[0].balance_cents == 99550


def test_no_balance_column_leaves_it_none():
    text = "Date,Description,Amount\n2026-07-01,Coffee,-4.50\n"
    rows = parse_csv(text)
    assert rows[0].balance_cents is None


# --- date formats -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("2026-07-01", datetime.date(2026, 7, 1)),
        ("07/01/2026", datetime.date(2026, 7, 1)),
        ("07/01/26", datetime.date(2026, 7, 1)),
        ("Jul 1, 2026", datetime.date(2026, 7, 1)),
        ("July 1, 2026", datetime.date(2026, 7, 1)),
    ],
)
def test_date_formats(raw, expected):
    # Quote the date field: several formats embed a comma ("Jul 1, 2026"), which would
    # otherwise misalign the CSV columns.
    text = f'Date,Description,Amount\n"{raw}",Coffee,-4.50\n'
    rows = parse_csv(text)
    assert rows[0].date == expected


def test_unrecognized_date_format_raises():
    text = "Date,Description,Amount\n2026.07.01,Coffee,-4.50\n"
    with pytest.raises(CsvParseError, match="Line 2"):
        parse_csv(text)


# --- amount formats ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected_cents",
    [
        ("-4.50", -450),
        ("4.50", 450),
        ("$4.50", 450),
        ("-$4.50", -450),
        ("$1,234.56", 123456),
        ("(12.34)", -1234),
        ("($1,234.56)", -123456),
        ("1500", 150000),
        ("0.01", 1),
    ],
)
def test_amount_formats(raw, expected_cents):
    # Quote the amount field: values like "$1,234.56" embed a comma, which would otherwise
    # misalign the CSV columns.
    text = f'Date,Description,Amount\n2026-07-01,X,"{raw}"\n'
    rows = parse_csv(text)
    assert rows[0].amount_cents == expected_cents


def test_unparseable_amount_raises():
    text = "Date,Description,Amount\n2026-07-01,X,not-a-number\n"
    with pytest.raises(CsvParseError, match="Line 2"):
        parse_csv(text)


# --- structural edge cases -----------------------------------------------------------------


def test_missing_date_column_raises():
    text = "Description,Amount\nCoffee,-4.50\n"
    with pytest.raises(CsvParseError, match="date"):
        parse_csv(text)


def test_missing_description_column_raises():
    text = "Date,Amount\n2026-07-01,-4.50\n"
    with pytest.raises(CsvParseError, match="description"):
        parse_csv(text)


def test_missing_amount_and_debit_credit_raises():
    text = "Date,Description\n2026-07-01,Coffee\n"
    with pytest.raises(CsvParseError, match="amount"):
        parse_csv(text)


def test_empty_file_raises():
    with pytest.raises(CsvParseError):
        parse_csv("")


def test_blank_trailing_row_is_skipped_not_an_error():
    text = "Date,Description,Amount\n2026-07-01,Coffee,-4.50\n2026-07-02,,\n"
    rows = parse_csv(text)
    assert len(rows) == 1


def test_blank_debit_and_credit_row_is_skipped():
    text = "Date,Description,Debit,Credit\n2026-07-01,Coffee,4.50,\n2026-07-02,,,\n"
    rows = parse_csv(text)
    assert len(rows) == 1
