# ARCHITECTURE.md — Magpie (software-level)

> **Status: Phases 0–3 built and deployed (2026-07-05).** Server: SSO-only auth, the full data
> model, `app/ledger/` (classify/rollups/balances, all pure and exhaustively tested),
> accounts/categories/transactions CRUD, and CSV reconciliation (`app/imports/`) are live at
> `https://dragonfly.tail2ce561.ts.net`. Android: Home/Transactions/CashEntry/Accounts on
> Retrofit+Room+Hilt+navigation-compose, with Roborazzi baselines for all four. **One known
> gap: the suite SSO client `magpie` is not yet registered on dragonfly-id**, so on-device
> sign-in can't complete end-to-end until that (small, additive) registration happens — see
> "Open items" below. **Also honest about scope: the CSV parser is generic/institution-agnostic**
> (no real Amex/Discover/US Bank sample exports were available to build per-issuer parsers
> against, unlike Phase −1's email corpus) — importing real 12-month history is a human step,
> not something fabricated here. Email ingestion/rules/bills/budgets (Phase 4+) are still
> target design — marked where it applies. Per the suite docs rule, convert each section to
> as-built language in the same PR that lands it. Suite-level context:
> `C:\Code\ARCHITECTURE.md`. Build spec + locked decisions: [CLAUDE.md](CLAUDE.md). Post-v1
> direction: [ROADMAP.md](ROADMAP.md).

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
- **`app/rules/`** — recurrence matching: cadence windows (biweekly/monthly ± slack),
  amount tolerance bands (rolling median ± pct, for seasonal utilities), merchant
  normalization + matching, transfer-match heuristics, and deviation detection (missing /
  out-of-band / short-paycheck). Deterministic and explainable — every auto-filed
  transaction can cite its rule.

### The ingestion pipeline (`app/ingest/`)

```
Gmail filters → label "magpie-ingest" → IMAP poll (lifespan task, every N min)
  → per-issuer parser template (amex.py / discover.py / usbank.py / …)
  → normalized event: card_swipe | deposit | ach_debit | bill_issued
  → dedupe (message-id + payload hash → ingest_events)
  → rules evaluation (see order below) → transaction row (pending) or bill_statement row
CSV/OFX import (monthly) → institution mapping → match pending→posted / create missed → import_batches
Manual entry (cash only) → same pipeline tail
```

**Testability seams (architectural):** four injected dependencies, each one interface with
a fake — the **clock** (`rules/` and all sweeps take `now`; every recurrence/expiry/
freshness test is a time-travel test), the IMAP fetcher, the LLM client, and the ntfy
publisher (alert tests assert **latching**: one publish per condition episode, not per
sweep). Nothing in the pipeline reads a wall clock or opens a socket directly.

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

Design rules: parsers are one module per issuer with **committed sanitized `.eml` fixtures**
(public repo — nothing real in git); an email that parses to nothing becomes an `unparsed`
ingest_event surfaced in an operator view + ntfy when the backlog grows, because a silently
broken parser is the pipeline's worst failure mode (the ledger quietly goes stale); the
ingest code never mutates the mailbox (read-only by behavior); every transaction carries
provenance (`source` + event/batch id) so any number is traceable to the email or CSV row
that produced it.

### Rules evaluation order (deterministic first, AI last — always)

1. dedupe → 2. transfer matching → 3. recurring income/bills (in-band ⇒ auto-filed) →
4. merchant→category rules → 5. LLM category suggestion ⇒ `needs_review` draft.
The review queue is the only place AI output meets the ledger, and only via user confirm —
the suite's draft-commit trust model applied to money.

**Cold start:** no rule auto-files until ≥3 observations (seeded by the Phase 3 twelve-month
CSV backfill — bands are rolling medians over matched history). **Scheduled sweeps** (same
lifespan scheduler as the poller): auth-hold expiry (pending, unmatched after ~7 days →
auto-drop with audit note), per-account freshness (no events in N days → staleness alert),
unparsed-backlog check. **Cash rule:** the ATM withdrawal *is* the spend (category `cash`);
manual cash entries are optional detail drawing that bucket down — never parallel spend.

### Domain map

**Built (Phase 0–3):** `app/main.py` (`/health`, `/version`), `app/routers/suite_auth.py` +
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
`StatementCheckpoint` when a Balance column is present. All ten §4 tables exist as SQLAlchemy
models (migration `0001`, unchanged since Phase 1 — Phases 2 and 3 both added zero migrations).

**Planned (Phase 4+):**

| Domain | Router | Service | Models |
|---|---|---|---|
| Rules | `rules.py` | `rule_service` (+ `rules/`) | `Rule` (exists) |
| Bills/calendar | `bills.py` | `bill_service` | `BillStatement` (exists) |
| Budgets | `budgets.py` | `budget_service` (+ `ledger/`) | `Budget` (exists) |
| Email ingestion | (poller, no router) | `app/ingest/` | `IngestEvent` (exists) |
| AI | `ai.py` | `services/ai/` (guardrailed) | drafts only, no writes |

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
Accounts) · `ui/transactions/TransactionsScreen` (list) · `ui/cashentry/CashEntryScreen` (the
offline-capable manual entry form) · `ui/accounts/AccountsScreen` (**Phase 3** — lists accounts
with computed balance + a "Reconciled"/"Off by $X" delta line when a checkpoint exists; each
row has an "Import CSV" action opening a dialog: institution field, `ActivityResultContracts
.GetContent()` file picker, multipart upload via `ApiService.importCsv`). `ui/navigation
/MagpieNavHost` gates the whole graph on `AuthGateViewModel.isSignedIn` (a `TokenStore` Flow) —
no explicit post-sign-in navigation call is needed, since saving a session makes the Flow
re-emit. Review queue · Bills calendar · Budgets · Settings are Phase 4+ (rules/bills/budgets
don't exist server-side yet either).

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

1. **Silent parser rot** (issuer redesigns its email) → unparsed-event counter + ntfy on
   backlog growth + fixtures pinning every template (sourced from the Phase −1 real-email
   corpus) + raw payloads kept in `ingest_events` with `parse_version` so a fixed parser
   **replays history** — a bad parse is recoverable, never permanent.
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
   reconciliation updates matched rows in place; the expiry sweep drops unmatched pendings
   after ~7 days with an audit note.
5. **Alert-coverage illusion** (an account quietly stops alerting) → per-account
   "last event seen" freshness on the Accounts screen + a staleness alert via ntfy.
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
