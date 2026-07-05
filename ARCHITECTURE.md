# ARCHITECTURE.md — Magpie (software-level)

> **Status: Phases 0–6 built and deployed (2026-07-05).** Server: SSO-only auth, the full data
> model, `app/ledger/` (classify/rollups/balances, all pure and exhaustively tested),
> accounts/categories/transactions CRUD, CSV reconciliation (`app/imports/`), email
> ingestion (`app/ingest/`), the rules engine + review queue, and bill matching + the first
> ntfy alert (`app/rules/`, `app/services/bill_service.py`/`sweep_service.py`) are live at
> `https://dragonfly.tail2ce561.ts.net`. Android: Home/Transactions/CashEntry/Accounts/
> Review-queue/Bills on Retrofit+Room+Hilt+navigation-compose, with Roborazzi baselines for
> all six. **Known gaps, all deliberate, none silent:**
> 1. The suite SSO client `magpie` is not yet registered on dragonfly-id, so on-device sign-in
>    can't complete end-to-end — see "Open items" below.
> 2. The CSV parser is generic/institution-agnostic (no real per-issuer sample exports were
>    available when it was built) — importing real 12-month history is a human step.
> 3. **Email ingestion has real parsers for exactly two issuers — Amex and US Bank — built
>    from the real Phase −1 corpus.** Discover has no email parser because it has no confirmed
>    real per-transaction alert email at all (its account-level preferences appear to route
>    alerts to push notifications instead); the Visa account named in CLAUDE.md's Phase −1
>    scope hasn't been checked this pass. Guessing at either would violate the entire point
>    of Phase −1 — coverage gaps are written down, not papered over with an untested parser.
> 4. **The live end-to-end proof of the ingestion pipeline is still pending a human step**:
>    Phase 4's IMAP poller needs real credentials for the dedicated ingestion mailbox
>    (account details in `C:\Users\Sonic\.dragonfly-suite\`), which requires finishing
>    Gmail's forwarding-address verification (blocked mid-setup by Google's own
>    anti-automation check) and then generating an app password. Everything upstream of
>    that credential is built and proven against real (sanitized) fixtures via a
>    mock-the-seam test — only the final "does a live
>    swipe really show up" proof is outstanding.
> 5. **Phase 5's rules engine auto-files transfers, recurring income/bills, and
>    merchant→category matches — but pending→posted matching (item 4's fast-follow) still
>    isn't built**, so a CSV-truth reconciliation pass won't yet merge with an email-sourced
>    pending row for the same swipe; they land as two rows until that lands.
> 6. **Phase 6's bill matching and "missing bill" detection are fully built and tested, but
>    there is still no `bill_issued` *email* parser for any issuer.** Real "statement ready"
>    emails with genuine structured data (statement date, balance) were confirmed for
>    Discover specifically during this phase — but the exact sender address couldn't be
>    confirmed (repeated attempts to open a sample email hit browser-automation flakiness),
>    and per the same Phase −1 discipline that kept Discover's transaction parser unbuilt,
>    guessing at the address here would be the same mistake. Bills exist today only via
>    `POST /bills` (manual/CSV-adjacent creation) — real bill-issued emails becoming
>    `BillStatement` rows automatically is a fast-follow once a sender is confirmed. Only
>    one of the four named alert sweeps (unparsed-email backlog) is built; auth-hold expiry,
>    per-account freshness, missing-bill, and paycheck-deviation alerts are not.
>
> Budgets + AI (Phase 7+) are still target design — marked where it applies. Per the suite
> docs rule, convert each section to as-built language in the same PR that lands it.
> Suite-level context: `C:\Code\ARCHITECTURE.md`. Build spec + locked decisions:
> [CLAUDE.md](CLAUDE.md). Post-v1 direction: [ROADMAP.md](ROADMAP.md).

Magpie is household cash-flow tracking with a review-not-enter product law: money events
arrive automatically (alert emails, monthly CSV), deterministic rules file the regular ones,
the local LLM drafts the rest, and the human sees a review queue and deviation alerts.

## System shape

```
Android (Kotlin/Compose) ⇄ Tailscale Serve (HTTPS, MagicDNS) ⇄ FastAPI :8005 ⇄ Postgres :5436
   phone must be on tailnet          │
   (ntfy precedent)                  ├→ IMAP (Gmail label "magpie-ingest") — in-process poller
                                     ├→ LM Studio :1234 (category drafts, insights)
                                     ├→ ntfy :8095 (topic magpie-alerts)
                                     └→ dragonfly-id JWKS (SSO verification, outbound HTTPS)
```

## Deviations from the suite app pattern (all deliberate, all locked)

| Suite norm | Magpie | Why |
|---|---|---|
| Public hostname via Cloudflare tunnel | **Tailnet-only** (Tailscale Serve fronts loopback :8005) | Financial data gets zero internet attack surface; phone is already on the tailnet |
| Password auth + optional SSO | **SSO-only** (no register/login endpoints) | BROKER.md 2e pilot; smallest possible auth surface |
| Synthetic smoke registers a password account | Smoke mints a **suite token** | No password path exists |
| Request-driven server only | **In-process background poller** (FastAPI lifespan task for IMAP) | First app needing scheduled ingestion; one container beats a worker sidecar at this scale |
| — | **Read-only invariant**: nothing on this box can move money | The security identity of the app |

Everything else follows Cookbook: compose layout (minus cloudflared), Alembic
migrate-on-boot, `/health` + `/version`, slowapi, pydantic-settings, NullPool test conftest,
Pulse composite build, suite signing/release/deploy conventions.

## Server design (`server/`)

### The two pure domain packages (the correctness core — no I/O, table-driven tests)

- **`app/ledger/`** (built, Phase 2–3) — `classify.py` (sign-convention enforcement: spend < 0,
  income/refund > 0, transfer-pair zero-sum invariant) + `rollups.py` (monthly income/spend/net,
  transfers excluded, refunds netted into spend not income) + `balances.py` (**Phase 3** — an
  account's OWN balance, deliberately distinct from the household rollup: it sums every
  transaction including transfer legs, since money genuinely moved through that specific
  account; `balance_delta` is the ledger-vs-statement honesty meter). 34 table-driven tests
  total. Per-category and vs-budget rollups are not built yet (Budgets CRUD is Phase 7 per
  CLAUDE.md's own phase list). If a number on the phone is wrong, the bug is here or in what
  feeds it — the `nutrition/` / `lists/merge.py` precedent.
- **`app/imports/csv_parser.py`** (built, Phase 3) — pure, no DB: auto-detects Date/
  Description/Amount-or-Debit+Credit/Balance columns from common header aliases (no real
  institution sample exports were available, so this is deliberately generic rather than
  per-issuer — see the status header). Handles `$1,234.56`, parenthetical-negative `(12.34)`,
  and six date formats. 28 tests.
- **`app/rules/`** (built, Phase 5) — `clock.py` (the injected time seam — `SystemClock` in
  production, `FixedClock` in tests, so cadence/band logic gets real time-travel tests)
  + `recurrence.py` (cadence windows — weekly/biweekly/monthly ± `slack_days`, monthly
  clamps to the last valid day so Jan 31 → Feb 28 doesn't crash) + `bands.py` (rolling
  median ± pct tolerance, compared on magnitude so a $45 bill and a refund-shaped -$45 read
  the same) + `merchant_match.py` (normalization strips card-network noise like `SQ *` /
  trailing transaction IDs, then substring match either direction) + `transfer_matching.py`
  (pairs an outflow on one account with an exactly-cancelling inflow on a *different*
  account within a day window — never same-account, never a partial match). All pure, 21
  table-driven tests. Deviation detection (missing bill / out-of-band / short-paycheck) is
  Phase 6, not built yet — the clock/band primitives exist, the alert sweeps that use them
  don't.

### The ingestion pipeline (`app/ingest/`)

```
Gmail filters → label "magpie-ingest" → IMAP poll (lifespan task, every N min)
  → per-issuer parser (amex.py / usbank.py — Discover/Visa: no real sample, no parser)
  → dedupe (message-id + payload hash → ingest_events)
  → account resolved by last4 hint → transaction row (status=pending, needs_review)
  → no matching account, or no recognized template → outcome="unparsed"
CSV/OFX import (monthly) → institution mapping → creates its own rows independently
  (pending↔posted matching against email-sourced rows is NOT built yet — see below)
Manual entry (cash only) → same pipeline tail
```

**Testability seams (architectural):** four injected dependencies, each one interface with
a fake — the **clock** (`rules/` and all sweeps take `now`; every recurrence/expiry/
freshness test is a time-travel test — not built yet, Phase 5), **the IMAP fetcher** (built,
Phase 4 — see below), the LLM client, and the ntfy publisher (alert tests assert **latching**:
one publish per condition episode, not per sweep — not built yet). Nothing in the pipeline
reads a wall clock or opens a socket directly.

**Built (Phase 1):** the suite-token test helper — `tests/conftest.py` generates one local RSA
keypair per test session and stubs the JWKS fetch, so tests mint valid RS256 suite tokens
without a real dragonfly-id (the only way to get an authenticated test client at all, since
Magpie has no password login). **Gotcha discovered building it:** `tests/` has no
`__init__.py`, so pytest's own conftest auto-discovery and a test file's
`from tests.conftest import suite_token` load **two separate module instances**, each running
the module-level keygen once — a token signed via one and verified via the other's JWKS fails
100% of the time. Fixed by exposing the helper as a fixture (`make_suite_token`) rather than an
importable function; fixtures always resolve through pytest's single cached module. Future test
files should request the fixture, not import the function.

**Built (Phase 4):** `app/ingest/parsers.py` — pure, no I/O — recognizes exactly two real
sender templates: Amex's "Large Purchase Approved" (spend) / "Merchant credit/refund was
issued" (refund), and US Bank's "A new Zelle payment..." / "You received a Zelle payment"
(income). Each extracts amount, merchant, date, and a last4 hint via regex against the real
Phase −1 corpus's structure; anything else — an unrecognized subject, a recognized subject
with no dollar figure, or a resolved parse with no matching account — raises `UnparsedEmail`
and becomes an `outcome="unparsed"` `ingest_event`, never a crash and never silent data loss.
**Two real bugs the tests caught before deploy:** the amount regex originally matched the
*first* dollar figure in an Amex body, which is the alert-threshold sentence ("...was more
than $1.00"), not the real charge that appears later — fixed to anchor on the *last* match.
And the merchant-extraction word-walk broke on a trailing hyphen a signed amount leaves behind
("...ONLINE -$18.00"), silently falling back to the entire flattened sentence — fixed by
stripping trailing separator punctuation first.

`app/ingest/imap_client.py` is the injected IMAP-fetcher seam: `RealImapFetcher` issues
`BODY.PEEK[]` (never plain `BODY[]`), so polling never sets the `\Seen` flag — the mailbox
stays read-only *by construction*, not just by convention (CLAUDE.md §8). Since flags are
never touched, "already processed" is tracked entirely by `ingest_events.message_id`, and
every poll re-scans a rolling window. `FakeImapFetcher` is the test double; `tests/fixtures/
*.eml` are sanitized (fabricated amounts/merchants/last4s) but structurally real, and
`test_ingest_service.py` feeds them through the actual parsers and a real throwaway DB — the
mock-the-seam E2E pattern, with only the socket faked. `app/ingest/poller.py` is the lifespan
background task (wired in `app/main.py`); it only starts if `imap_host` is configured, the
same "absence disables the feature" pattern as `suite_jwks_url`. `GET /ingest/events` is the
unparsed-backlog operator view; `POST /ingest/poll` triggers an out-of-band poll for
verification without waiting out the interval.

**Not built yet, called out rather than silently skipped:** pending→posted matching against
CSV truth (an email-sourced pending transaction and a later CSV-imported posted row for the
same swipe currently become two separate rows, not one reconciled row — a real fast-follow,
not folded into Phase 4 since it also touches Phase 3's `import_service.py` matching logic);
the rules engine (Phase 5) that would auto-file recurring matches instead of leaving
everything `needs_review`; the clock-driven sweeps (auth-hold expiry, freshness alerts); and
the ntfy unparsed-backlog alert. **The live proof of the whole pipeline — a real swipe
appearing as a pending transaction within one poll interval — has not happened yet**: it
needs IMAP credentials for the dedicated ingestion mailbox, which is blocked on finishing
Gmail's forwarding verification (see the status header). What's shippable *right now* is
everything upstream of that one external credential.

Design rules: parsers are one module per issuer with **committed sanitized `.eml` fixtures**
(public repo — nothing real in git); an email that parses to nothing becomes an `unparsed`
ingest_event surfaced in an operator view (+ ntfy on backlog growth, once Phase 6 lands ntfy)
because a silently broken parser is the pipeline's worst failure mode (the ledger quietly
goes stale); the ingest code never mutates the mailbox (read-only by behavior, enforced via
`BODY.PEEK[]`, not just documented); every transaction carries provenance (`source` +
`ingest_event_id`) so any number is traceable to the email that produced it.

### Rules evaluation order (deterministic first, AI last — always)

**Built (Phase 5), wired into both `import_service.py` and `ingest_service.py` so every
CSV row and every ingested email goes through the same evaluator — `app/services
/rule_service.py::evaluate_transaction`:** 1. dedupe (already done upstream by each caller
before a row ever reaches the evaluator) → 2. transfer matching (an exact-cancelling pair on
a different account ⇒ both legs `kind="transfer"`, `review_state="auto"`, no review) →
3. recurring income/bill rules (≥3 observations + within cadence window + within amount band
⇒ auto-filed with `rule_note` = `"Matched rule: X"`; below threshold or out of band ⇒
`needs_review` with an explanation naming the rule and the reason) → 4. merchant→category
rules (deterministic category assignment ⇒ auto) → 5. LLM category suggestion ⇒
`needs_review` draft — **not built yet, Phase 7**; today, falling through all four rule
stages just leaves a transaction `needs_review` with no draft category. **A rule only ever
decides *category*, never *kind*** — the amount's sign is the single source of truth for
spend/income/refund (`app/ledger/classify.py`), so a mismatched rule can never force an
invalid sign combination onto a transaction.

**Cold start:** no rule auto-files until ≥3 observations, counted from *every* matching
transaction on that account regardless of whether it predates the rule — Phase 3's CSV
backfill history counts the same as live events, exactly as CLAUDE.md's cold-start bar
intends. Below threshold, the review queue shows *why* ("Looks like XCEL ENERGY, 2/3
observations"), not just that it needs a look.

**Bill matching (built, Phase 6):** `app/rules/bill_matching.py` — pure — pairs a
`BillStatement` to the closest-dated payment on its bound account (CLAUDE.md §2: each
biller rides one payment rail) within a 10-day window either side of the due date, exact
amount only; `is_bill_missing` answers the time question (due date + a 3-day grace passed,
still unmatched) that `app/services/bill_service.py` combines with "no match yet" to decide
`is_missing`. `POST /bills` tries an immediate match (a backfilled historical bill
shouldn't sit "missing" forever) and `POST /bills/{id}/rematch` re-checks after a later
import/poll brings in the settling payment.

**Alert latching (built, Phase 6):** `app/rules/alerts.py::should_alert` — pure, fires only
on the true rising edge (a condition becoming true), stays silent while it persists, and
fires again if it resolves and recurs — exactly CLAUDE.md's "once per episode, not once per
sweep" bar, proven with a fake-clock-free logic test plus a real DB-backed
`test_sweep_service.py` exercising all three cases. **`app/services/ntfy_client.py`** is the
fourth and final injected seam (clock, IMAP fetcher, ntfy publisher, LLM client — the LLM
client is still Phase 7): `FakeNtfyPublisher` records what would have been sent,
`HttpNtfyPublisher` POSTs for real. **Built and wired into a lifespan sweep loop: exactly
one alert** — the unparsed-email backlog, latched, checked every `sweep_interval_minutes`.
**Not built yet:** auth-hold expiry, per-account freshness, missing-bill, and
paycheck-deviation sweeps — `app/rules/clock.py`'s `Clock` seam and the bill-matching/rule
primitives they'd need already exist; nothing schedules them yet. **Cash rule** (the ATM
withdrawal *is* the spend, manual cash entries draw that bucket down) is still target
design, not built.

### Domain map

**Built (Phase 0–6):** `app/main.py` (`/health`, `/version`), `app/routers/suite_auth.py` +
`app/services/suite_auth.py` (suite login), `app/routers/auth.py` (`POST /auth/refresh` — a
Phase 1 gap: refresh tokens were minted but nothing could redeem them until this landed),
`app/security.py` (local HS256 session tokens). Full CRUD for accounts, categories, and
transactions (`app/routers/{accounts,categories,transactions}.py` +
`app/services/{account,category,transaction}_service.py`), all scoped to `CurrentUser` by
filtering on `user_id` in the query itself (never a separate ownership check — a cross-user
`test_*_not_visible_to_a_different_user` test pins this per domain). `GET /transactions/summary`
is the Home month-panel read, backed by `app/ledger/rollups.py`; `AccountOut` now carries
computed `balance_cents`/`balance_delta_cents` (`app/ledger/balances.py`). `POST /imports/csv`
(`app/routers/imports.py` + `app/services/import_service.py`) parses via `csv_parser.py`,
dedupes against existing transactions by an (account, date, amount, description) fingerprint
(no message-id to key on, unlike email ingestion), creates `needs_review` transactions
(kind guessed from sign only — a CSV row is never a manual confirmation), and optionally a
`StatementCheckpoint` when a Balance column is present. `POST /ingest/poll` + `GET
/ingest/events` (`app/routers/ingest.py` + `app/services/ingest_service.py`) are the email
pipeline's manual-trigger and operator-view surface. All ten §4 tables exist as SQLAlchemy
models; migration `0002` (Phase 4) added `ingest_events.raw_payload` (the actual body, not
just its hash — needed so a fixed parser can replay history, which the Phase 1 migration's
comment promised but the columns didn't yet back) plus `account_id`/`user_id` for scoping.
Migration `0003` (Phase 5) added `rules.user_id` (the same CurrentUser-scoping gap
`ingest_events` had before Phase 4, caught the same way) plus `transactions
.matched_rule_id`/`rule_note` — the review queue's "why", captured as a fact at evaluation
time rather than re-derived later from whatever the rule looks like now. `GET/POST /rules`,
`GET/PATCH/DELETE /rules/{id}` (`app/routers/rules.py` + `app/services/rule_service.py`) are
plain CurrentUser-scoped CRUD; `PATCH /transactions/{id}` gained `review_state` and `kind`
(the review queue's confirm/correct action — `kind` only re-validates the sign invariant
when supplied, never blindly trusted); `GET /transactions?review_state=needs_review` is the
review queue's read. `GET/POST /bills`, `POST /bills/{id}/rematch` (`app/routers/bills.py` +
`app/services/bill_service.py`) — no migration needed: `BillStatement.account_id` is
required, so it scopes via the same join-to-`Account.user_id` pattern Phase 3's
`StatementCheckpoint` already established, no nullable-join gap to close. `is_missing` is
computed at read time (`_to_out()`, mirroring `AccountOut`'s balance fields from Phase 3),
never stored.

**Planned (Phase 7+):**

| Domain | Router | Service | Models |
|---|---|---|---|
| Budgets | `budgets.py` | `budget_service` (+ `ledger/`) | `Budget` (exists) |
| AI | `ai.py` | `services/ai/` (guardrailed) | drafts only, no writes |

**Deferred fast-follow, not a full phase:** pending→posted matching between email-sourced and
CSV-sourced rows for the same swipe (see the ingestion pipeline section above).

## Android design (`android/`, package `com.magpie`)

Suite MVVM (Room + Retrofit + Hilt), Pulse composite build, **teal accent**
(`PulseAccent.Teal` — added to the library in Phase 0). Channel semantics (`MagpieTheme.kt`):
teal = money/primary, green = income/under-budget, amber = needs-review, a red channel built
locally from Pulse's proven `PulseRed`/`PulseRedDeep` (not a new library accent) =
over-budget/deviation.

**Built (Phase 2):** `data/remote/` — `ApiService` (Retrofit + kotlinx-serialization),
`AuthInterceptor` + `TokenRefreshAuthenticator` (mirrors Spotter/Cookbook's hardened
authenticator: serialized refreshes, only an explicit auth rejection signs out, a transient
network failure mid-refresh keeps the session), `SuiteAuthManager` (AppAuth PKCE — see the open
item below). `data/local/db/` — `PendingCashEntryEntity` + `CashEntryDao` (Room, the offline
cash-entry queue only — no broader read cache yet). `data/repository/TransactionRepository` —
the write-through: tries the server immediately, catches only `IOException` (genuine offline)
to queue locally, lets any HTTP error propagate as a real bug rather than a silent queue (5
repository tests against fakes pin this distinction, the `nutrition`/`merge.py`-style
correctness core on the client side). `util/NetworkSyncObserver` drains the queue on
reconnect (Cookbook's `NetworkSyncObserver` precedent).

Screens: `ui/signin/SignInScreen` ("Sign in with Dragonfly," the only auth path) ·
`ui/home/HomeScreen` (month in/out/net panel via `HomeContent`, gates on having ≥1 account —
shows an inline create-account form instead of the summary when none exist, and now links to
Accounts, Review queue, and Bills) · `ui/transactions/TransactionsScreen` (list) ·
`ui/cashentry/CashEntryScreen` (the offline-capable manual entry form) ·
`ui/accounts/AccountsScreen` (**Phase 3** — lists accounts with computed balance + a
"Reconciled"/"Off by $X" delta line when a checkpoint exists; each row has an "Import CSV"
action opening a dialog: institution field, `ActivityResultContracts.GetContent()` file
picker, multipart upload via `ApiService.importCsv`) · `ui/reviewqueue/ReviewQueueScreen`
(**Phase 5** — `GET /transactions?review_state=needs_review`; each row shows the amount,
merchant, and `rule_note` when a rule fired but didn't clear the auto-file bar — CLAUDE.md's
"the review queue shows why" made literal on-screen, not just a server-side concept; a
"Confirm" action `PATCH`es `review_state="confirmed"`) · `ui/bills/BillsScreen` (**Phase 6**
— `GET /bills`; each row shows the biller, due date, and a Paid/Missing/Awaiting-payment
status derived from `matched_transaction_id`/`is_missing`, not a full "due before next
paycheck" calendar view yet — that cross-reference against a paycheck rule's cadence isn't
built). `ui/navigation/MagpieNavHost` gates the whole graph on
`AuthGateViewModel.isSignedIn` (a `TokenStore` Flow) — no explicit post-sign-in navigation
call is needed, since saving a session makes the Flow re-emit. Budgets · Settings are Phase
7+ (budgets don't exist server-side yet either). **Not built this pass:** badge counts on
Home for the review queue's size or the bills-missing count (CLAUDE.md's target design) —
both screens exist, the Home-panel summary of either doesn't yet.

Each screen splits into a thin ViewModel-wired composable and a pure `*Content` composable
taking plain state + callbacks (`HomeScreen` → `HomeContent`, `AccountsScreen` →
`AccountsContent`) — the Roborazzi baselines screenshot the pure half directly, so no Hilt DI
is needed in the screenshot test. **A real layout bug was caught this way in Phase 2**: three
`StatTile`s in a `Row` without `weight()` silently overflowed off-frame — the recorded PNG
was the thing that surfaced it, not code review.

Offline model: the **only entry surface that's offline is cash entry** (the Room queue above);
everything else is online-first against the tailnet — no broader read cache yet (unlike
Cookbook's recipe cache). Acceptable because the phone is on Tailscale wherever it has signal.
Because Tailscale Serve provides HTTPS, the manifest needs **no cleartext exception** (unlike
Hawksnest's bare-IP problem).

### Open item: the `magpie` suite OAuth client isn't registered yet

`SuiteAuthManager` is wired for client id `magpie`, redirect `com.magpie:/oauth2redirect` — the
naming CLAUDE.md's Phase 8 section already commits to. But dragonfly-id's static client list
(`Dragonfly/server/app/oidc/clients.py`) only has `spotter`/`plate`/`cookbook`/`dragonfly`/
`localdev` today. **On-device sign-in cannot complete until `magpie` is added there** — a small,
additive change to a live production identity server, deliberately not made without a separate
go-ahead (same caution as the Pulse `PulseAccent.Teal` change: touching shared/live suite
infrastructure gets its own explicit authorization, not a silent side effect of an app-repo
task). CLAUDE.md's own Phase 8 scopes this registration there; it may make sense to pull it
forward once someone wants to actually test the sign-in flow on a phone.

## Trust boundaries

1. **Internet → Magpie: none.** No public DNS, no tunnel. Reachability = tailnet membership.
2. **Mailbox → Magpie:** a read-scoped-by-behavior IMAP session using a dedicated app
   password/OAuth token in `server/.env`; parser output is untrusted input (validated,
   bounded, deduped) — an attacker who can email you should at worst create a
   `needs_review` draft, never an auto-filed transaction (rules only auto-file against
   *learned history*, not novel senders).
3. **AI:** LM Studio local-only, sees DB-derived context (never raw emails), output
   Pydantic-validated, persists only through user confirmation.
4. **Money movement: impossible by construction** — no credentials with write power exist
   in this system, and no feature may introduce them (see ROADMAP.md non-goals: no bill pay).
5. **Backups:** Magpie's dumps ride the nightly NAS pipeline, which must be encrypted at
   rest first (host ROADMAP2 Tier 1 #10 — blocking precondition).

## Failure modes to design for (ranked)

1. **Silent parser rot** (issuer redesigns its email) → unparsed-event counter (built, Phase 4:
   `GET /ingest/events?outcome=unparsed`; the ntfy backlog alert itself is still Phase 6) +
   fixtures pinning every template (sourced from the Phase −1 real-email corpus) + raw
   payloads kept in `ingest_events.raw_payload` with `parse_version` so a fixed parser
   **replays history** — a bad parse is recoverable, never permanent. Already proved useful
   once: two real parser bugs (an amount regex anchored on the first dollar figure instead of
   the last, a merchant-name walk that broke on trailing punctuation) surfaced as test
   failures before deploy, not as silently wrong dollar amounts in production.
2. **Double-count via transfers or cash** → `ledger/` transfer semantics + pairing tests
   (every `transfer_group` sums to zero) + the ATM-is-the-spend cash rule; these are the
   classic self-built-tracker bugs and they're designed out at the model layer.
3. **Balance drift from reality** (unknown opening balance, missed events, interest) →
   `statement_checkpoints` (built, Phase 3) anchor the ledger to each statement's stated
   balance; the per-account delta is surfaced on the Accounts screen ("Reconciled" / "Off by
   $X"), and the **statement-parity gate** (two consecutive months to the penny
   post-reconciliation) remains v1's acceptance criterion — real bank CSVs, not the synthetic
   fixtures the parser is tested against, are what that gate actually measures.
4. **Pending/posted drift** (tip adjustments) and **auth holds that never post** → CSV
   reconciliation updates matched rows in place (not built); the expiry sweep drops
   unmatched pendings after ~7 days with an audit note (not built — `app/rules/clock.py`'s
   seam exists, nothing schedules this sweep yet).
5. **Alert-coverage illusion** (an account quietly stops alerting) → per-account "last event
   seen" freshness + a staleness alert via ntfy — **not built**; the one alert that exists
   today (Phase 6) is the unparsed-email backlog, not per-account freshness.
6. **Tailscale outage** → app degrades to cached reads; ingestion pauses and catches up
   (IMAP is pull — nothing is lost, the label retains the mail).

## Operational fit (host-side, lands in Phase 8)

Monitoring a tunnel-less app needs its own answer: **uptime-kuma** watches
`http://host.docker.internal:8005/health` (server liveness — kuma is a container and can't
reach the tailnet mapping), while **`Test-SuiteInvariants.ps1`** watches what kuma can't:
`tailscale serve status` still carries the Magpie mapping. The invariant checker also needs
a **per-app exception list** — Magpie legitimately fails the suite-wide
`COMPOSE_PROFILES=tunnel` assertion, and must be exempted *before* first deploy or it pages
a false alarm. Config distribution: the hub's broker serves `config/magpie` (the ts.net
base URL) to the app's `SuiteConfigReader`, same as siblings. Backups: magpie-db rides the
nightly `*-db-1` dump pipeline (verify the glob picks it up) — which is itself gated on the
encrypted-dumps precondition.
