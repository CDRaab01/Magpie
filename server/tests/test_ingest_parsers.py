from datetime import date

import pytest

from app.ingest.parsers import UnparsedEmail, parse_amex, parse_email, parse_usbank

AMEX_PURCHASE_BODY = """
Dear SENTINEL USER,

As you requested, we're letting you know that this purchase on your Additional
Card ending 000000 was more than $1.00.

TEST MERCHANT CO
$42.00*

Sun, Jul 5, 2026
"""

AMEX_REFUND_BODY = (
    "See the merchant credit details SENTINEL USER Account Ending: 0000 "
    "Your account has been credited Here's more information about any merchant "
    "credits you received SAMPLE STORE ONLINE -$18.00"
)

USBANK_ZELLE_BODY = """
Log in

A new payment of $75.00 from Jordan Q Sample was deposited in your account.
Credited to account ending in: 0000
Received date: 07/02/2026
"""


def test_amex_large_purchase_is_negative_spend():
    event = parse_amex("Large Purchase Approved", AMEX_PURCHASE_BODY)
    assert event.kind == "spend"
    assert event.amount_cents == -4200
    assert event.merchant == "TEST MERCHANT CO"
    assert event.event_date == date(2026, 7, 5)
    assert event.last4_hint == "0000"


def test_amex_merchant_credit_is_positive_refund():
    event = parse_amex("Merchant credit/refund was issued to your account", AMEX_REFUND_BODY)
    assert event.kind == "refund"
    assert event.amount_cents == 1800
    assert event.merchant == "SAMPLE STORE ONLINE"
    assert event.last4_hint == "0000"


def test_amex_unrecognized_subject_is_unparsed():
    with pytest.raises(UnparsedEmail):
        parse_amex("Your account has been credited", "irrelevant body")


def test_amex_recognized_subject_without_amount_is_unparsed():
    with pytest.raises(UnparsedEmail):
        parse_amex("Large Purchase Approved", "no dollar figure in this body at all")


def test_usbank_zelle_payment_is_positive_income():
    event = parse_usbank("A new Zelle payment is in your account.", USBANK_ZELLE_BODY)
    assert event.kind == "income"
    assert event.amount_cents == 7500
    assert event.merchant == "Jordan Q Sample"
    assert event.event_date == date(2026, 7, 2)
    assert event.last4_hint == "0000"


def test_usbank_non_zelle_subject_is_unparsed():
    with pytest.raises(UnparsedEmail):
        parse_usbank("Your mailing address has changed", "irrelevant body")


def test_parse_email_dispatches_by_exact_sender():
    event = parse_email(
        "AmericanExpress@welcome.americanexpress.com",
        "Large Purchase Approved",
        AMEX_PURCHASE_BODY,
    )
    assert event.parser == "amex"


def test_parse_email_unknown_sender_is_unparsed():
    with pytest.raises(UnparsedEmail):
        parse_email("someone@unknown-issuer.example.com", "Subject", "body")
