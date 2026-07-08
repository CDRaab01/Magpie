from datetime import date

import pytest

from app.ingest.parsers import (
    UnparsedEmail,
    parse_amex,
    parse_discover,
    parse_email,
    parse_usbank,
)

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

# Constructed for the F7 direction test (no real "sent" sample exists in the Phase -1 corpus;
# sentinel values only, per the public-repo fixture rule).
USBANK_ZELLE_SENT_BODY = """
Log in

You sent a payment of $30.00 to Alex Sample.
Debited from account ending in: 0000
"""

# US Bank's account-wide "Your transaction is complete." alert — one subject, direction in the
# body ("transaction of" = debit/spend, "deposit of" = money in/income). No merchant is carried.
USBANK_TRANSACTION_BODY = """
Log in

Your transaction of $42.00 is complete.
To review this transaction, log in and view your account ending in 0000.
"""

USBANK_DEPOSIT_BODY = """
Log in

Your deposit of $1,000.00 is complete.
To review this transaction, log in and view your account ending in 0000.
"""

DISCOVER_ALERT_BODY = """
Account Center - Last 4 #: 0000

A transaction above the limit you set has been initiated.

No action is needed.

Merchant: TEST MERCHANT CO
Date: July 06, 2026
Amount: $25.00

The amount shown might be a pending pre-authorization amount.
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


def test_usbank_zelle_received_is_positive_income():
    event = parse_usbank("A new Zelle payment is in your account.", USBANK_ZELLE_BODY)
    assert event.kind == "income"
    assert event.amount_cents == 7500
    assert event.merchant == "Jordan Q Sample"
    assert event.event_date == date(2026, 7, 2)
    assert event.last4_hint == "0000"


def test_f7_usbank_zelle_sent_is_negative_spend_not_income():
    # The F7 bug: an outbound "You sent a Zelle payment" alert used to book as positive income.
    event = parse_usbank("You sent a Zelle payment", USBANK_ZELLE_SENT_BODY)
    assert event.kind == "spend"
    assert event.amount_cents == -3000
    assert event.merchant == "Alex Sample"


def test_f7_usbank_zelle_ambiguous_direction_is_unparsed():
    # Subject matches "zelle payment" but the body reveals neither direction — never assume
    # income; surface it for the operator instead.
    with pytest.raises(UnparsedEmail):
        parse_usbank("A Zelle payment notification", "A payment of $10.00 was processed.")


def test_usbank_non_zelle_subject_is_unparsed():
    with pytest.raises(UnparsedEmail):
        parse_usbank("Your mailing address has changed", "irrelevant body")


def test_usbank_transaction_complete_is_negative_spend():
    event = parse_usbank("Your transaction is complete.", USBANK_TRANSACTION_BODY)
    assert event.kind == "spend"
    assert event.amount_cents == -4200
    assert event.merchant is None  # US Bank's transaction alert carries no merchant
    assert event.last4_hint == "0000"


def test_usbank_deposit_complete_is_positive_income():
    # Same subject as a debit — direction ("deposit of") is read from the body. This is the
    # paycheck path (#17): US Bank does email deposits.
    event = parse_usbank("Your transaction is complete.", USBANK_DEPOSIT_BODY)
    assert event.kind == "income"
    assert event.amount_cents == 100000
    assert event.last4_hint == "0000"


def test_usbank_transaction_without_direction_is_unparsed():
    with pytest.raises(UnparsedEmail):
        parse_usbank("Your transaction is complete.", "Something happened. $5.00. account 0000")


def test_discover_transaction_alert_is_negative_spend():
    event = parse_discover("Transaction Alert", DISCOVER_ALERT_BODY)
    assert event.kind == "spend"
    assert event.amount_cents == -2500  # from "Amount: $25.00", not the boilerplate
    assert event.merchant == "TEST MERCHANT CO"
    assert event.event_date == date(2026, 7, 6)
    assert event.last4_hint == "0000"


def test_discover_unrecognized_subject_is_unparsed():
    with pytest.raises(UnparsedEmail):
        parse_discover("You have a new statement", DISCOVER_ALERT_BODY)


def test_discover_alert_without_amount_line_is_unparsed():
    with pytest.raises(UnparsedEmail):
        parse_discover("Transaction Alert", "A transaction was initiated. No action is needed.")


def test_parse_email_dispatches_by_exact_sender():
    event = parse_email(
        "AmericanExpress@welcome.americanexpress.com",
        "Large Purchase Approved",
        AMEX_PURCHASE_BODY,
    )
    assert event.parser == "amex"


def test_parse_email_dispatches_discover_by_sender():
    event = parse_email(
        "discover@services.discover.com",
        "Transaction Alert",
        DISCOVER_ALERT_BODY,
    )
    assert event.parser == "discover"


def test_parse_email_unknown_sender_is_unparsed():
    with pytest.raises(UnparsedEmail):
        parse_email("someone@unknown-issuer.example.com", "Subject", "body")
