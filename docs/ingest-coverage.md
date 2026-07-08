# Ingest coverage note (Phase −1)

> **Purpose (CLAUDE.md §10, Phase −1 exit criterion):** a living, one-page record of *which
> issuer alerts on what*, proving per-account alert coverage empirically **before** the Phase 4
> parser architecture bets on it. Every real example earmarked here becomes a sanitized `.eml`
> fixture later (CLAUDE.md §9 — never commit a real amount/merchant/last-4).
>
> Fill the tables as labeled mail arrives. **Exit:** ≥2 weeks of labeled mail across all four
> accounts + this note complete.

Status: **Parsers built for Amex + US Bank + Discover (updated 2026-07-08).** Real
per-transaction alert coverage confirmed and filtered on the *main* Gmail; Magpie reads that
account's `magpie-ingest` label directly over IMAP (see the routing decision below — the
dedicated forwarding mailbox was dropped). Real sender addresses and subject templates are
captured in `server/app/ingest/parsers.py` and its sanitized `.eml` fixtures. **Only remaining
step to go live: the main-account app password (`[H]`).**

- **Amex** — `AmericanExpress@welcome.americanexpress.com`. Two real per-transaction
  templates confirmed: "Large Purchase Approved" (spend, $1 threshold) and "Merchant
  credit/refund was issued to your account" (refund). A Gmail filter on this sender +
  those two subjects applies label `magpie-ingest`, retroactively applied to existing mail.
- **US Bank** — `usbank@notifications.usbank.com`. **Two templates (updated 2026-07-08):**
  the account-wide **"Your transaction is complete."** (body says "Your transaction of $X" for a
  debit→spend, "Your deposit of $X" for money in→income — this *is* the paycheck path, confirmed
  by a real $4,061.55 deposit) **and** the Zelle alert ("A new Zelle payment…"/"You received a
  Zelle payment"). The earlier Zelle-only gap is closed. No merchant in the transaction alert —
  CSV fills it.
- **Discover** — `discover@services.discover.com`. **Now emailing (updated 2026-07-08):** a
  **"Transaction Alert"** per charge with clean labeled fields (`Merchant:`/`Date:`/`Amount:`/
  `Last 4 #:`). Phase −1 had found it push-only; the owner's alert setup changed that. Parser
  built (`parse_discover`, spend; the amount is a pending pre-auth reconciled from CSV). Discover
  also sends "You have a new statement" (bill-issued, not yet parsed — Phase 6).
- **Visa** — **out of v1** (owner enabled alerts on US Bank/Amex/Discover only, 2026-07-08).
- **Combined corpus so far:** 58 real historical conversations retroactively labeled
  (Amex + US Bank combined, spanning back to 2024) — used as the basis for the sanitized
  fixtures Phase 4 ships with, in place of a strict "2 weeks live" wait.

**Routing decision (2026-07-08): main-account IMAP, not forwarding.** The dedicated-mailbox +
forwarding plan was **abandoned** — Gmail's forwarding-address verification repeatedly hit
Google's anti-automation wall and the confirmation email never arrived. Instead, a single Gmail
filter on the main account (`from:(the 3 senders) subject:(the transaction subjects)`) applies
`magpie-ingest`, and Magpie's poller connects to the **main account** and selects the
**`magpie-ingest` label** (`IMAP_USER` + `IMAP_LABEL=magpie-ingest`). The dedicated mailbox
(address on file in `~\.dragonfly-suite\`) and its app password are no longer used. Tradeoff accepted: the
main-account app password can technically read the whole inbox, mitigated by read-only poller
behavior (`BODY.PEEK`, label-scoped).

**Not yet done / open:**
1. **`[H]` Generate the main-account Google app password** (`magpie-imap-main`) → save to
   `C:\Users\Sonic\.dragonfly-suite\magpie-main-imap.txt` → it becomes `IMAP_PASSWORD` in
   `server/.env`, with `MAGPIE_IMAP_HOST=imap.gmail.com` + `MAGPIE_IMAP_USER` in the host root
   `.env`. Until then the compose IMAP vars default empty ⇒ the poller stays off.
2. **The live end-to-end proof** (a real swipe becomes a pending transaction within one poll
   interval) is blocked only on #1; everything upstream is built + tested against sanitized
   fixtures (`server/tests/test_ingest_parsers.py`, `test_ingest_service.py`).
3. **Bill-issued email parser** (Phase 6) — Discover "You have a new statement" carries a real
   statement date + balance; parse it when Phase 6's bill pipeline needs it.

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
