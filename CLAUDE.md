# CLAUDE.md — "Magpie"

> Personal household finance: cash flow in both directions, assembled automatically from
> transaction-alert emails + monthly CSV reconciliation, reviewed — never entered — by the
> human. Sixth app in the suite alongside **Spotter** (fitness), **Plate** (nutrition),
> **Cookbook** (recipes/groceries), **Hawksnest** (home), **Dragonfly** (hub/identity).
> Same stack, same conventions, same PULSE design language.
>
> Spec drafted 2026-07-04 from the owner-approved design discussion (departing-engineer
> handoff, round 2). Decisions marked **locked** were confirmed by the owner — do not
> relitigate them without new information.

---

## 0. Read this first

Work **phase by phase**; do not start a later phase before the earlier one's exit criteria
(tests green, CI green) are met. When a decision is ambiguous, **match Cookbook** — it carries
the suite's newest conventions (`C:\Code\Cookbook`, see its CLAUDE.md + ARCHITECTURE.md), and
new apps copy Cookbook by suite policy. Before writing code in any phase: restate the phase
goal, list the files you'll touch, flag any assumption, then proceed.

Magpie **deliberately breaks two suite patterns** (both locked — see §2 and §8):
1. **Tailnet-only.** No public hostname, no cloudflared tunnel. Exposure is via Tailscale
   Serve (HTTPS at the host's MagicDNS name). This is the security posture for financial data.
2. **SSO-only auth.** No `/auth/register`, no password `/auth/login` — suite tokens via
   dragonfly-id exclusively. Magpie is the pilot for BROKER.md 2e.

**Blocking precondition before real financial data enters the DB:** host ROADMAP2 Tier 1 #10
(encrypt the NAS DB dumps at rest) must be done — financial history must never sit plaintext
on the household share. Verify, don't assume.

## 1. Product summary

Magpie answers *"where does the money actually go — and what's about to go out?"*

The core loop is **review, not entry** (the design's one hard product law — manual-entry
budget apps die of drift): transactions arrive automatically, deterministic rules file the
regular ones, the local LLM proposes categories for the rest, and the human's daily job is a
ten-second review queue plus push alerts only when reality deviates from the model.

1. **Automatic capture** of card spend (Amex/Discover/Visa per-transaction alert emails),
   checking activity (US Bank deposit/withdrawal alerts — paychecks in, ACH bills out), all
   through one Gmail-label → IMAP → parser pipeline.
2. **Monthly CSV/OFX reconciliation** as the source of truth (pending→posted correction,
   gap-filling for checks and weak-alert issuers). Manual entry exists only for cash.
3. **Rules engine**: recurring income ("~$X from EMPLOYER every other Friday"), recurring
   bills with tolerance bands (utilities vary seasonally), transfer matching (card payments
   net to zero). Deviations alert via ntfy: paycheck late/short, bill missing, bill over band.
4. **Bills forecast / cash-flow calendar**: biller "statement ready" emails are ingested as a
   distinct *bill-issued* event and matched to later payments — "due before next paycheck"
   is a first-class screen, not an afterthought.
5. **Budgets**: monthly amount per category, month-vs-budget view, review-queue-first Home.
6. **AI (local, guardrailed)**: categorization suggestions for unmatched transactions and
   periodic plain-language insights — always drafts, never auto-committed, no revenue
   conflict of interest by construction.

## 2. Locked decisions (owner-confirmed 2026-07-04 — do not relitigate)

- **Ingestion tiers:** (A) alert-email parsing + (B) CSV/OFX reconciliation are v1.
  (C) **SimpleFIN Bridge** (read-only aggregator, ~$15/yr) is the designed escape hatch,
  built **only if** A+B coverage proves insufficient in practice — see ROADMAP.md for the
  trigger conditions. **Plaid-style credential storage is permanently out.**
- **Read-only invariant (the app's #1 security law):** Magpie never stores credentials or
  tokens capable of *moving money*. Bank creds never touch this box; any future aggregator
  token must be read-only-scoped. A full compromise leaks history, never funds.
- **Tailnet-only** via Tailscale Serve (HTTPS, MagicDNS). No Cloudflare tunnel, no public DNS.
  The phone is already on the tailnet (ntfy precedent). Precedent for the mechanism:
  Hawksnest's planned TLS uses the same approach.
- **SSO-only**; accounts come from dragonfly-id (client id `magpie`). Note the synthetic-smoke
  convention: sibling smokes register throwaway *password* accounts — Magpie's smoke must
  mint a suite token instead (see §9).
- **Accounting semantics:** transactions are **signed**; accounts are typed
  (`card` | `depository`); **card payments are transfers** (matched pair, nets to zero — the
  double-count trap); **card refunds are negative spend in the original category, never
  income**; each biller is bound to one payment rail (its rule lives on one account);
  **auth holds expire** (a pending with no posted match after N days — default 7 — auto-drops
  with an audit note, gas-station $1 pre-auths being the canonical case); **the ATM
  withdrawal is the cash spend** (category `cash`) — manual cash entries are optional detail
  that draw that bucket down, never parallel spend (the cash double-count rule).
- **Balance anchoring:** every CSV/statement import records the institution's stated balance
  as a `statement_checkpoint`; the Accounts screen shows the **ledger-vs-statement delta**
  per account. A nonzero delta is a data-quality signal, not cosmetics — it is the app's
  honesty meter and the input to the statement-parity acceptance gate (§9).
- **Net income only.** No gross pay, withholding, 401k decomposition, or anything
  tax-adjacent. (Paystub-photo-to-draft is a documented non-goal, not a backlog item.)
- **Ports 8005 (API) / 5436 (Postgres)** — the reserved next-free pair in `C:\Code\CLAUDE.md`.
- **Pulse accent:** Magpie leads **teal** — requires adding `PulseAccent.Teal` to the Pulse
  library (superset-safe: new enum case + palette family, no existing-consumer impact; follow
  Pulse/ARCHITECTURE.md "how to change Pulse safely").
- **Public repo** (CDRaab01/Magpie, like the siblings): code public, data private. Therefore
  **all committed parser fixtures must be sanitized** (fake amounts/merchants/last-4s) and
  gitleaks-style hygiene applies from commit one.

## 3. Architecture (target — see ARCHITECTURE.md for the full design)

```
Android (Kotlin/Compose) ⇄ FastAPI :8005 (tailnet-only via Tailscale Serve) ⇄ Postgres :5436
                                 │
                                 ├→ IMAP poll (Gmail label "magpie-ingest") — in-process worker
                                 ├→ LM Studio :1234 (categorization drafts, insights)
                                 └→ ntfy :8095 topic magpie-alerts (deviation alerts)
```

- Backend: FastAPI + SQLAlchemy 2.0 async + Alembic, Cookbook's layout
  (`app/routers|services|models|schemas`) plus **two pure domain packages** (the
  nutrition/merge precedent): `app/ledger/` (signed math, transfer/refund semantics,
  budget rollups — table-driven tests, no I/O) and `app/rules/` (recurrence matching,
  tolerance bands, transfer pairing — pure, exhaustively tested).
- **`app/ingest/`**: IMAP client + per-issuer parser templates (amex/discover/usbank/…,
  one module each, committed sanitized `.eml` fixtures), event normalization
  (`card_swipe | deposit | ach_debit | bill_issued`), dedupe (message-id + content hash).
  The poller is an in-process asyncio task started in FastAPI lifespan (no second container).
- CSV importer: per-institution column mappings, `import_batches` provenance,
  match-or-create against pending events.
- AI in `app/services/ai/` per the Spotter guardrail contract: server-side prompts, Pydantic-
  validated output, suggestions are drafts, no autonomous writes, no tool access.
- Android: suite MVVM (Room + Retrofit + Hilt), Pulse via composite build. Offline: read
  cache + offline **cash-entry** queue (the one entry surface); everything else online
  (tailnet ≈ always reachable when it matters).

## 4. Data model (backend)

- `accounts` — id, user_id, name, institution, type (`card`|`depository`), last4, active.
- `transactions` — id, account_id, **amount (signed, cents)**, currency, date, posted_at,
  status (`pending`|`posted`), merchant_raw, merchant_norm, category_id, kind
  (`spend`|`income`|`transfer`|`refund`), transfer_group (nullable — pairs net to zero),
  review_state (`auto`|`needs_review`|`confirmed`), source (`email`|`csv`|`manual`),
  ingest_event_id / import_batch_id provenance, created_at.
- `categories` — seeded sensible set + user CRUD; `budgets` — category_id, month, amount.
- `rules` — type (`recurring_income`|`recurring_bill`|`transfer_match`|`merchant_category`),
  account_id, matcher (merchant pattern), cadence, amount_band (median ± pct), category_id,
  last_matched_at, enabled. Deterministic; evaluated before any AI suggestion.
- `bill_statements` — biller, account_id (payment rail), amount_due, due_date, issued_at,
  matched_transaction_id (nullable until paid) — powers the cash-flow calendar +
  missing-bill alerts.
- `statement_checkpoints` — account_id, statement_date, stated_balance, import_batch_id —
  the balance anchors (§2). Derived ledger balance is always computed *between* checkpoints;
  the per-account delta against the latest checkpoint is surfaced on the Accounts screen.
- `ingest_events` — raw provenance: message_id, received_at, parser, parse_version,
  payload_hash, outcome (`created`|`duplicate`|`unparsed`). Unparsed events surface in an
  operator view — a silent parser break is the pipeline's worst failure mode.
- `import_batches` — file hash, institution, row counts, created/matched/skipped.
- `users` — dragonfly-id linkage (email), settings. No password hash columns needed
  (SSO-only), but keep the column layout Cookbook-compatible where free.

## 5. The rules engine (deterministic first, AI second — in that order, always)

Evaluation order for every new event: (1) dedupe; (2) transfer matching (outflow from
checking ≈ a card's recent balance/payment → pair + net to zero, no review); (3) recurring
rules (income + bills; within band → auto-filed `auto`); (4) merchant→category rules;
(5) **only then** the LLM proposes a category → `needs_review` draft. Rule hits are
deterministic and explainable ("matched rule: XCEL monthly ±20%"); the review queue shows
*why* something needs a human.

**Cold start:** a recurrence rule may not auto-file until it has **≥3 observations** (from
backfill history or live events); before that threshold its matches route to review with
the rule named ("looks like XCEL, 2/3 observations"). Bands compute from a rolling median
of the matched history — which is why the Phase 3 **historical backfill** (~12 months of
CSV per account) is a build step, not a nicety: without it the app spends its first months
asking about everything.

**Sweeps** (same scheduler as the IMAP poller): auth-hold expiry (§2), per-account
freshness ("no events from Discover in 9 days" — silent alert-decay detection), unparsed
backlog. Alerts (ntfy topic `magpie-alerts`): expected-bill-missing (cadence window
passed), amount-out-of-band (with median context), paycheck late/short, account gone
stale, parser-unparsed backlog > 0.

## 6. AI guardrails

Spotter's CLAUDE.md "AI Guardrails" is the contract; Magpie's specifics: prompts server-side
in `app/services/ai/`; the model sees transaction context from the DB (trusted) and never
raw emails; output is Pydantic-validated category suggestions / insight text; **nothing the
model produces is persisted without explicit user confirmation**; no tool/DB/file access;
insights carry no product placements by definition — that's the point of the app. Scope:
descriptive finance ("dining out doubled since March"), never investment/tax/legal advice.

**Amendment (2026-07-11, owner-requested budget coach):** within the **coach and chat
surfaces only** (`ai/coach.py`, `ai/chat.py`), the model MAY be prescriptive about the
household's **own spending measured against its own budgets and stated savings goal**
("dining is on pace for $180 against your $150 budget — tailor it back"), grounded strictly
in the provided aggregates. Investment/tax/legal advice and product recommendations remain
banned everywhere; the retrospective monthly insight (`ai/insight.py`) remains
descriptive-only; and every AI-suggested budget or goal change remains a draft the owner
explicitly confirms — the coach's plans are computed on request and never persisted at all.

## 7. Screens (Android)

Home (month cash-flow panel: in vs out vs budget, review-queue badge, upcoming-bills strip) ·
Review queue (approve/correct drafts — the primary interaction) · Transactions (filter/search,
signed ledger) · Bills / cash-flow calendar ("due before next paycheck") · Budgets
(month-vs-budget by category) · Accounts (per-account balances-as-derived, alert-coverage
status) · Settings (rules editor, category editor, About). Teal-led PULSE; channel semantics:
**teal** = money/primary, **green** = income/under-budget, **amber** = needs-review/warning,
**red-family** (from the shared palette) = over-budget/deviation.

## 8. Security posture (this section is load-bearing)

1. Read-only invariant (§2). 2. Tailnet-only via Tailscale Serve; server binds loopback,
Serve fronts it with HTTPS — the Android client uses the `https://…ts.net` URL, so **no
cleartext exception in the manifest**. 3. SSO-only; JWKS verification identical to siblings
(`SUITE_JWKS_URL`/`SUITE_ISSUER` pinned in compose `environment:` per suite invariant #4).
4. Gmail access (**revised 2026-07-08**): the poller connects to the **main account** with a
Google app password (2FA on) in `server/.env` and selects the **`magpie-ingest` label** only.
_Original plan was a dedicated forwarding mailbox (so the credential saw only alerts); Gmail
forwarding proved too fragile — its verification kept hitting Google's anti-automation wall — so
the app now reads the main account scoped to the label instead._ Tradeoff: the app password can
technically read the whole inbox, mitigated because the ingest module is **read-only by
behavior** — `BODY.PEEK` only, never marks/moves/deletes/sends, and only ever selects the label.
See ARCHITECTURE.md "email ingestion". 5. Sanitized fixtures only in the public
repo. 6. Encrypted-backup precondition (§0). 7. Rate limits + security headers as siblings;
`/health` + `/version` are the only unauthenticated endpoints (and they're tailnet-only
anyway).

## 9. Testing & CI

**Testability is architectural — the seams come first:** an injectable **clock provider**
server-side (the Spotter `TimeProvider` precedent, applied to Python: `rules/` and the
sweeps take `now` as a dependency, never call it) because *everything* interesting here is
time-dependent — cadence windows, tolerance-band aging, auth-hold expiry, freshness alerts
— and every one of those tests is a time-travel test ("advance 40 days, assert the
missing-bill alert fired"). The IMAP fetch, the LLM client, and the ntfy publisher are the
other three seams; each is one interface with a fake. Nothing in the pipeline may reach for
a wall clock, a socket, or a mailbox directly.

- **Ledger + rules math**: table-driven, exhaustive (signs, transfer pairing, refund
  semantics, band edges, cadence windows) — the `nutrition/`/`merge.py` precedent; these
  two packages are the app's correctness core. Include the invariant tests: every
  `transfer_group` sums to zero; totals are stable under event reordering; **re-import is
  idempotent** (same CSV twice ⇒ byte-identical ledger).
- **Alert latching**: deviation alerts must fire **once per condition episode**, not once
  per sweep (a missing bill must not page every 15 minutes). The latch state is data,
  tested with the fake clock: condition arises → one publish; sweeps repeat → silence;
  condition resolves and recurs → one new publish.
- **Parser fixtures**: committed sanitized `.eml` per issuer template, sourced from the
  **Phase −1 corpus** (real emails, sanitized); a parser change must keep every fixture
  green; unparsed-event regression test. Raw payloads persist in `ingest_events` with a
  `parse_version` so a parser fix can be **replayed over history** — a bad parse is
  recoverable, never permanent.
- **Mock-the-seam E2E** (the Hawksnest `mock-ha` precedent): the IMAP fetch is one seam;
  tests feed real `.eml` files through the entire pipeline (parse → dedupe → rules →
  transaction) with no live mailbox.
- **Statement parity — the v1 acceptance gate**: after monthly CSV reconciliation, the
  ledger matches every account's statement **to the penny for two consecutive months**
  before the alert pipeline is trusted as primary. The `statement_checkpoints` delta makes
  this a visible number. This is Magpie's airplane-mode test — the proof of the product's
  core promise.
- Router tests against a throwaway DB (**127.0.0.1**, `DB_NULLPOOL` — conftest per Cookbook);
  IMAP + LM Studio + ntfy always mocked in CI. **Migration smoke** in CI: alembic upgrade
  head against a fresh Postgres service container (dragonfly-id's `server-ci.yml` precedent).
- **Auth in tests**: mint suite-style RS256 tokens against a test JWKS (dragonfly-id's
  `localdev` client / Cookbook's suite_auth tests are the reference) — there is no password
  path to lean on.
- **Fixture sanitization guard**: a CI test asserting every committed `.eml` fixture uses
  only the sentinel values (last4 `0000`, sentinel merchant names, amounts from the test
  table) — the public-repo backstop behind manual sanitization; gitleaks runs too but
  doesn't know what a real merchant looks like.

### CI/CD inventory (workflow shapes cloned from Cookbook; deltas in bold)

- `ci.yml` — gitleaks (suite standard) · ruff + `ruff format --check` · pytest (Postgres
  service, migration smoke) · Android unit + Roborazzi (baselines from Phase 2 — never a
  baseline-less job, Cookbook lesson) · assembleDebug (Pulse sibling checkout) · weekly
  `schedule:` with the scheduled-only `pip-audit` job (suite Tier 1 #3 pattern) ·
  Dependabot from day one (grouped weekly, majors ignored, AGP/Kotlin/Compose/KSP
  name-pinned).
- `release.yml` — on `android/**` pushes to main: suite key, `version.json`
  (epoch-minute versionCode), apksigner pin, Pulse checkout.
- `deploy.yml` — `workflow_run` after CI on main (guarded `event == 'push'`), runner label
  `magpie` (new Windows service `C:\actions-runner-magpie`), `vars.MAGPIE_DIR`,
  `redeploy.ps1` **no-tunnel variant**, health gate on loopback `/health`. **Magpie-specific
  CD hardening: `redeploy.ps1` takes a `pg_dump` snapshot BEFORE `docker compose up -d
  --build`** (keep last 5 in the repo-adjacent backups dir) — migrations run on boot against
  financial history; a bad migration must be a restore, never a loss. **No `pull_request`
  triggers on self-hosted jobs** (suite invariant #7).
- **Synthetic smoke** (deploy gate): suite-token mint → create manual cash transaction →
  read → delete, inside the server container per the suite runner gotcha (host ROADMAP.md
  T2 #3). **SSO-only makes the token mint the one nontrivial bit** — there is no
  register/login to script. Decision owed in Phase 1 (recommendation: a dedicated
  confidential smoke client on dragonfly-id — client-credentials grant issuing a
  **suite-audience token for a designated throwaway smoke email**, the `CROSS_APP_CLIENTS`
  mechanism's shape with `aud=suite` — small, auditable, and revocable independently).

**What CI structurally cannot test** — Tailscale Serve, the real mailbox, real LM Studio —
is owned by the post-deploy smoke, the uptime-kuma loopback monitor, the invariant
checker's `tailscale serve status` assertion, and the per-account freshness sweeps. Name
the gap; don't pretend the pyramid covers it.

## 10. Build phases (each ends with green tests + green CI)

**Phase −1 — corpus collection (ZERO CODE, human task, START IMMEDIATELY — before Phase 0)**
Turn on per-transaction alerts on all four accounts (Amex, Discover, the Visa's issuer,
US Bank — cards: any-amount transaction alerts; checking: deposit + withdrawal alerts,
threshold $1) and create the Gmail filters → label `magpie-ingest`. Also enable each
biller's "statement ready" email where offered. Every week that passes builds the parser
corpus and **empirically proves per-issuer alert coverage** before the architecture bets on
it — if the Visa's issuer only alerts card-not-present, we learn it here for free, not in
Phase 4. Exit: ≥2 weeks of labeled mail across all accounts; a one-page coverage note in
this repo (which issuers alert on what, with real examples earmarked for sanitized fixtures).

**Phase 0 — scaffold + the two pattern departures**
Repo skeleton mirroring Cookbook (server `/health` + `/version`, Android shell on Pulse,
CI both sides). Add `PulseAccent.Teal` to Pulse (built against ≥1 existing consumer before
push). Compose = `db` + `server` only (**no cloudflared**); document the Tailscale Serve
command in `deploy/README.md`. Exit: empty app builds teal; CI green; `/health` reachable
via the tailnet HTTPS URL.

**Phase 1 — SSO-only auth + data model**
`POST /auth/suite` (Cookbook's implementation, minus password endpoints entirely) + all §4
tables in migration 0001+. **Decide the smoke-auth mechanism here** (§9 recommendation: a
confidential smoke client on dragonfly-id issuing a suite-audience token for a throwaway
smoke email) — it's a dragonfly-id change, so land it before Phase 8 needs it. Exit: sign
in with Dragonfly on-device against tailnet Magpie; schema migrates clean; suite-token test
helper in place; smoke-auth decision recorded here.

**Phase 2 — signed ledger core (manual + CRUD)**
Accounts/categories/transactions CRUD, `app/ledger/` with transfer/refund semantics, manual
cash entry (with offline queue on Android), Transactions + Home screens. Exit: ledger math
exhaustively tested; a hand-entered month reads correctly on-device; first Roborazzi
baselines recorded.

**Phase 3 — CSV/OFX reconciliation + historical backfill + balance anchors**
Importer + institution mappings + `import_batches` + dedupe/matching +
`statement_checkpoints` (stated balance per import; Accounts screen shows the
ledger-vs-statement delta). Then the **backfill**: import ~12 months of CSV history per
account — it seeds the rules engine's medians (cold-start §5) and makes "since March"
insights possible from day one. Exit: a real (local, uncommitted) Amex/Discover/US Bank CSV
imports idempotently — re-import creates zero dupes — and the backfilled year reconciles to
each account's checkpoints. **The v1 acceptance gate starts counting here: two consecutive
live months of to-the-penny statement parity (§9) before the alert pipeline is considered
primary.**

**Phase 4 — email ingestion pipeline**
Gmail label + filters (operator doc), IMAP poller (lifespan task), issuer parser templates
+ sanitized fixtures, pending→posted matching against CSV truth, unparsed-event operator
view. Exit: a live swipe appears as a pending transaction within one poll interval;
fixtures green; unparsed backlog visible.

**Phase 5 — rules engine + review queue**
`app/rules/` + rules CRUD + the evaluation order (§5) + Review queue screen. Exit: paycheck,
card-payment transfer, and ≥3 bills auto-file with rule explanations; queue holds only
genuine unknowns.

**Phase 6 — bills forecast + alerts**
`bill_issued` parsing, `bill_statements` matching, cash-flow calendar screen, ntfy alerts
(missing bill / out-of-band / paycheck deviation / unparsed backlog). Exit: "due before next
paycheck" renders truthfully; a simulated missing bill pages the phone.

**Phase 7 — budgets + AI layer**
Budgets CRUD + month-vs-budget; LLM categorization drafts for rule-misses; first insights
surface (guardrailed, draft-only). Exit: guardrail tests green (mocked LLM); review queue
shows AI suggestions distinctly from rule hits.

**Phase 8 — suite membership + release + operational fit**
`release.yml` (suite key, `version.json`, apksigner pin), deploy runner + redeploy.ps1
(no-tunnel variant) + synthetic smoke. Dragonfly-side: registry entry + `<queries>` +
`ServiceRegistry` row (SUITE probe via the tailnet URL — the Hawksnest "off-network" state
already handles tailnet probes) + dragonfly-id client `magpie` + a **config-broker entry**
(`config/magpie` serving the ts.net base URL; Magpie's Android app carries
`util/SuiteConfigReader` like its siblings — the tailnet URL is exactly what the broker
exists to distribute). Host-side operational fit, in the same phase: **teach
`Test-SuiteInvariants.ps1` a per-app exception list** (Magpie legitimately has no
`COMPOSE_PROFILES=tunnel` — without the exemption its first deploy pages a false alarm) and
add its checks (magpie runner service, `.env` ACL, `tailscale serve status` carries the
mapping); **uptime-kuma monitor** on `http://host.docker.internal:8005/health` → ntfy
(Serve config itself is watched by the invariant checker, since kuma can't see the tailnet
mapping from a container); magpie-db joins the nightly backup + restore-drill set (verify
the generic `*-db-1` glob picks it up). Exit: merge-to-main ships an APK the hub can
install; hub Suite status shows Magpie green; invariant checker green *with* Magpie
running; a killed server pages the phone; ROADMAP2/host CLAUDE.md rows updated from
"planned" to live.

## 11. Conventions & guardrails

- Match Cookbook's code style, package naming (`com.magpie`), workflow shapes; if this file
  conflicts with how Cookbook/Spotter actually do something, **the existing apps win** —
  flag the conflict.
- Ledger/rules math centralized and pure; clients display, never compute.
- Alembic migrations only; Pydantic at every boundary; amounts are **integer cents**, never
  floats.
- Keep the ARCHITECTURE.md in this repo updated as phases land (same-PR rule) — it starts
  as a design doc and must become as-built.
- Personal-use tool, descriptive not advisory — no investment/tax advice in prompts or copy.
  (Narrow exception: the budget coach/chat may coach against the owner's own budgets/goal —
  see the §6 amendment, 2026-07-11.)
