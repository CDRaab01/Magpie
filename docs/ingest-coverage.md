# Ingest coverage note (Phase −1)

> **Purpose (CLAUDE.md §10, Phase −1 exit criterion):** a living, one-page record of *which
> issuer alerts on what*, proving per-account alert coverage empirically **before** the Phase 4
> parser architecture bets on it. Every real example earmarked here becomes a sanitized `.eml`
> fixture later (CLAUDE.md §9 — never commit a real amount/merchant/last-4).
>
> Fill the tables as labeled mail arrives. **Exit:** ≥2 weeks of labeled mail across all four
> accounts + this note complete.

Status: **Phase 4 built against Amex + US Bank (2026-07-05).** Real per-transaction alert
coverage confirmed and filtered on the *primary* Gmail (account details in
`C:\Users\Sonic\.dragonfly-suite\`) — not yet
routed through the dedicated mailbox described below. Real sender addresses and subject
templates are now captured directly in `server/app/ingest/parsers.py` and its sanitized
`.eml` fixtures, superseding the placeholder guesses originally in this doc.

- **Amex** — `AmericanExpress@welcome.americanexpress.com`. Two real per-transaction
  templates confirmed: "Large Purchase Approved" (spend, $1 threshold) and "Merchant
  credit/refund was issued to your account" (refund). A Gmail filter on this sender +
  those two subjects applies label `magpie-ingest`, retroactively applied to existing mail.
- **US Bank** — `usbank@notifications.usbank.com`. One real template confirmed: "A new
  Zelle payment is in your account" / "You received a Zelle payment" (income/deposit, no
  confirmed threshold). Filtered the same way. **Gap:** this only covers Zelle P2P deposits
  — no confirmed coverage yet for paycheck ACH deposits or ACH/check debits on this account;
  CSV reconciliation is the fallback for those until real examples surface.
- **Discover** — alert *preferences* were confirmed enabled in the account UI (2026-07-05),
  but **zero real per-transaction alert emails have arrived** despite that — an AI-assisted
  inbox summary suggested Discover may route these to push notifications rather than email.
  No Discover parser exists; guessing at one would defeat Phase −1's purpose. Check Discover's
  actual notification-channel setting directly before building anything here.
- **Visa** — still not identified/enabled. Untouched this pass.
- **Combined corpus so far:** 58 real historical conversations retroactively labeled
  (Amex + US Bank combined, spanning back to 2024) — used as the basis for the sanitized
  fixtures Phase 4 ships with, in place of a strict "2 weeks live" wait.

**Not yet done / open:**
1. **Primary → dedicated forwarding** (to the dedicated ingest mailbox, address on file in
   `C:\Users\Sonic\.dragonfly-suite\`) is configured but
   **not verified** — Gmail's own anti-automation check ("secure Google verification...
   try again later") interrupted setup mid-flow. A real, unhurried manual click is more
   likely to succeed than another scripted attempt. An app password for the dedicated
   mailbox already exists (`C:\Users\Sonic\.dragonfly-suite\magpie-ingest-mailbox.txt`),
   but is not yet wired into `server/.env` since the mail flow it would authenticate isn't
   live yet.
2. **Whether the dedicated mailbox needs its own `magpie-ingest` label at all is now an
   open question, not a fixed step** — once forwarding is scoped to *only* the Amex/US Bank
   filters (never a blanket forward), every message landing in the dedicated account's
   INBOX is by definition Magpie-relevant; the IMAP poller could simply select `INBOX`
   there instead of requiring a second, redundant label filter. Decide this before wiring
   `IMAP_LABEL` in production config.
3. **Visa** — identify the issuer, enable its per-transaction alert if one exists.
4. **The live end-to-end proof** (a real swipe becomes a pending transaction within one
   poll interval) is blocked on steps 1–2 above; everything upstream is built and tested
   against sanitized fixtures (see `server/tests/test_ingest_service.py`).

## Accounts in scope

| # | Institution | Type | Last-4 | App-facing name | Alerts enabled? | First labeled mail |
|---|---|---|---|---|---|---|
| 1 | American Express | `card` | ____ | Amex | ☑ $1 | — |
| 2 | Discover | `card` | ____ | Discover | ☑ (thr TBD) | — |
| 3 | **Visa — issuer: ______** | `card` | ____ | Visa | ☐ | — |
| 4 | US Bank | `depository` | ____ | US Bank checking | ☑ ≥$10 | — |

> **Open item:** the Visa's issuing bank is unconfirmed in the spec ("the Visa's issuer"). Record
> it above — it determines the sender domain to filter on and whether it alerts per-transaction at
> all (some Visa issuers only alert on card-not-present / over-threshold — exactly the coverage gap
> Phase −1 exists to find *now*, not in Phase 4).

## Per-issuer alert coverage (fill from real mail)

For each issuer, what event types actually arrive by email, and the exact `From:` address the
Phase-4 parser will key on.

| Issuer | Sender address (verified from real mail) | Card swipe | Deposit | Withdrawal / ACH | "Statement ready" / bill-issued | Notes on threshold / gaps |
|---|---|---|---|---|---|---|
| Amex | _e.g._ `AmericanExpress@welcome.americanexpress.com` | ☑ (≥$1) | n/a | n/a | ☐ | **Use the "Large Purchase notification" alert — $1 minimum (confirmed UI 2026-07-05) → near-total coverage.** (The separate "Charge Over Amount" alert floors at $10; ignore it in favor of Large Purchase.) Strong real-time source. |
| Discover | _e.g._ `discover@services.discover.com` | ☑ | n/a | n/a | ☐ | enabled 2026-07-05 (threshold: ____ — confirm) |
| Visa (____) | ______ | ☐ | n/a | n/a | ☐ | **CNP-only? over-threshold-only?** |
| US Bank | _e.g._ `usbank@service.usbank.com` | n/a | ☑ (≥$10) | ☑ (≥$10) | ☐ | **$10 minimum on deposit + withdrawal alerts (confirmed UI 2026-07-05).** Weak real-time source for small checking activity — sub-$10 deposits/withdrawals not alerted; caught by CSV reconciliation. Consequential for mid-month cash balance (§ "due before next paycheck"). Confirm: was withdrawal one toggle or split (debit/ACH/check/ATM)? |

*(Sender addresses above are typical defaults, NOT verified for this mailbox — replace each with
the real `From:` once the first alert lands.)*

## Earmarked fixtures (real → sanitized, for Phase 4)

| Gmail message (subject + date) | Issuer | Event type | Sanitized fixture filename (planned) |
|---|---|---|---|
| | | | `server/app/ingest/fixtures/amex_swipe.eml` |
| | | | `server/app/ingest/fixtures/discover_swipe.eml` |
| | | | `server/app/ingest/fixtures/usbank_deposit.eml` |
| | | | `server/app/ingest/fixtures/usbank_ach_debit.eml` |

## Gmail routing — DEDICATED FORWARDED MAILBOX (decided 2026-07-05)

**Architecture decision (refines CLAUDE.md §8.4 — fold into §8.4 + ARCHITECTURE.md on next commit):**
Magpie's stored IMAP credential opens a **dedicated Gmail account** containing *only* bank alerts,
NOT the owner's primary Gmail. Rationale: least privilege on the stored token — a server
compromise leaks transaction history (the risk tier Magpie already accepts, §2) instead of the
primary inbox (password-reset / account-recovery root). Isolation is **structural** (a separate
account) rather than merely behavioral (label scoping on the primary).

Flow:
1. Banks send alerts to the **primary** Gmail (account details in
   `C:\Users\Sonic\.dragonfly-suite\`) — bank email-on-file is
   **unchanged** (statements / fraud / security mail stay in primary).
2. A **primary-side filter** auto-**forwards** the verified alert senders → the dedicated account.
   (Forward = a copy; original stays in primary, searchable.)
3. The **dedicated account** labels incoming alerts **`magpie-ingest`** (hard-coded expectation —
   ARCHITECTURE.md ingestion pipeline, `ingest_event` model) and has **IMAP enabled** + an
   **app password** (2FA on). Phase 4's poller opens this box only.

The mailbox is read-only *by our code's behavior* (§8.4) — the pipeline only reads + dedupes,
never moves/deletes/sends. Forwarding filters live in Gmail, outside Magpie.

- Dedicated address: on file in `C:\Users\Sonic\.dragonfly-suite\` (created 2026-07-05; app password in
  `C:\Users\Sonic\.dragonfly-suite\magpie-ingest-mailbox.txt` — never commit it here)
- Forwarding verified in primary: ☐   ·   IMAP enabled on dedicated: ☐   ·   app password issued: ☑
