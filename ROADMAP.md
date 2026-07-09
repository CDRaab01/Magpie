# ROADMAP.md — Magpie (rewritten 2026-07-09: the single forward roadmap)

> **This file is now the only forward-looking plan.** The history lives elsewhere:
> CLAUDE.md §10 (the original build phases, all shipped), [V1.md](V1.md) (the 2026-07-05
> tier plan + the F1–F18 findings — now a build record; its remaining open items were folded
> in here), and [ARCHITECTURE.md](ARCHITECTURE.md) (as-built). Rewritten after the 2026-07-09
> roadmap review: the correctness core is fixed, Tier 4 UI parity essentially landed, and the
> old plan had decayed into a changelog — the remaining work was scattered through ✅
> annotations and "still to do" fragments inside completed items.
>
> This plan is organized around the two things the app still lacks: **proof on real money**
> (Wave 0) and **the product's second act** (Waves 1–3: the money made visible, the AI
> actually awake, and the features the pitch implied). Waves are dependency buckets like
> V1.md's tiers: Wave 1 is code-only and can start today; Wave 2 is pointless before Wave 0's
> backfill; Wave 3 builds on both. `[H]` = needs the owner's hands, credentials, or eyes.
> Locked decisions (CLAUDE.md §2) and the non-goals at the bottom are unchanged and not up
> for relitigation.

## Where the app actually stands (2026-07-09)

Live and healthy on the host (tailnet-only, SSO-only; CI → Release → Deploy green; `/version`
matches `main`). Every 2026-07-05 code-review finding is closed except the F13/F15 remnants
below. Email ingestion is live against the real corpus (Amex / US Bank / Discover parsers);
rules + review queue with corrections and "make this a rule", bills, budgets, cash-flow
calendar, transaction splits, rules editor, onboarding, deep-linked alerts, and the Tier 4
suite-parity pass (bottom bar, hero, content Home, color grammar, ~28 Roborazzi baselines)
have all shipped.

**But:** the ledger has never held a real dollar (one "Test" account; 22 real Amex alerts
sit unfiled), the production LLM has never fired (`llm_base_url` unset — the AI stage
silently skips), and no screen draws a single chart — the suite's most numbers-heavy app is
its only member with zero data visualization (no `Sparkline`, `ProgressRing`, `TickerNumber`,
or Canvas anywhere, while Plate's Home leads with a ring + ticker + sparkline and Spotter has
a full animated trend chart).

## Wave 0 — v1 exit: prove it on real money

**The critical path is data, not code.** The gate chain below is strictly ordered; everything
else in this wave can run in parallel with it.

1. **[H] Create the real accounts** (Amex, US Bank checking, Discover — with last4s). New
   alerts auto-file the moment these exist; the 22 already-seen stay unfiled until the replay
   tool (#7) retro-files them.
2. **[H] 12-month CSV backfill** per account via the Accounts screen. Expect parser
   reality-fixes — that's the point. While here: confirm **Discover's sign convention**
   against the real export (extend `institution_mappings.py`; almost certainly
   positive-is-charge, left out per the don't-guess rule) and **decide whether the Visa is in
   scope for v1** (never checked in Phase −1; no decision recorded). The backfill seeds the
   rules engine's medians (cold start §5) and is the precondition for Wave 2's AI being
   worth anything.
3. **[H] Anchor checkpoints and drive every account to "Reconciled"** — then the
   **statement-parity clock starts**: two consecutive to-the-penny months (§9, the v1
   acceptance gate). Mostly elapsed time plus a monthly reconciliation habit.
4. **[H] Paycheck path:** confirm whether US Bank deposit alerts actually arrive by email
   (the parser already handles "deposit of" if so); if not, document that paycheck detection
   is CSV-only and the recurring-income rule keys off history alone.

Code items, all unblocked now:

5. **The two remaining sweeps.** **Auth-hold expiry** — a pending row >7 days with no posted
   match auto-drops with an audit note (§2; the first data-*mutation* sweep — same clock/latch
   seams, new shape). **Paycheck-short** — band-based, detected at ingestion when a
   recurring-income match lands under band; pages with median context.
6. **Bill-matching guards (F13).** Filter the candidate pool by sign/kind so a same-magnitude
   deposit can't "pay" a bill; enforce one bill per matched transaction.
7. **Parser replay tool (F15), then the `bill_issued` parser.** The replay script over
   `ingest_events.raw_payload` + `parse_version` finally has a real customer — the 22
   pre-account alerts — and every future parser fix needs it. Build it first. The Discover
   statement-ready parser follows **[H]** once the owner confirms the real sender address
   (browser flakiness blocked that confirmation last time; don't guess).
8. **Small UI debts from Tier 4:** AI-suggestion text gets its own violet voice and teal is
   pared back to brand/primary + money-totals (#31's tail); inline editing of a rule's
   band/cadence (the editor is enable/disable/delete today); the `flip_sign` override
   checkbox in the import dialog (server param exists).
9. **Fixture-sanitization CI guard** (V1 Tier 5 #39): a test asserting every committed `.eml`
   uses sentinel values only (last4 `0000`, `SENTINEL` merchants). A real PII leak already
   happened once this build; gitleaks doesn't know what a merchant looks like.
10. **[H] The accumulated on-device batch:** formal SSO sign-in confirmation (real-use
    feedback on v0.1.65 suggests it works — mark it), split-sheet interaction, encrypted
    token store (F17), tap one real alert deep link, font-scale/TalkBack pass, and one human
    eyeball over the ~28 Roborazzi baselines (the wrapped-money lesson).
11. **Ops loose ends:** verify the uptime-kuma monitor exists and pages; clean/document the
    smoke user's prod residue; update host `C:\Code\CLAUDE.md` + ROADMAP2's Magpie rows from
    "planned" to live; backup passphrase → password manager + offsite copy **[H]**.

**v1 is done when:** parity holds for two consecutive months, the owner runs the daily review
from the phone, a simulated missing bill and a short paycheck both page it, and the on-device
batch is signed off.

## Wave 1 — See the money (charts + read models; code-only, can start today)

The genre's core question — *where does the money actually go?* — is a visual question, and
Magpie currently answers it entirely in prose and single numbers. Pulse already ships the
vocabulary (`Sparkline` in line/filled/bars modes, `ProgressRing`, `TickerNumber`, the dense
`StatTile` with an icon/animatedValue/sparkline slot) and the siblings prove the idioms
(Plate's calorie ring with a `TickerNumber` inside + weekly protein sparkline; Spotter's
animated custom-Canvas trend chart with grid + reveal). Per the cross-check rule: reuse these
exact components and idioms; invent nothing new.

12. **Server read models** (pure `app/ledger/` additions + thin routers; table-driven tests;
    owner-local month boundaries per F18):
    All four live under one `/summary` router (avoids colliding with the categories router's
    `/{id}` route). **Server side DONE 2026-07-09** (`app/services/summary_service.py` +
    `app/routers/summary.py`, pure math added to `app/ledger/rollups.py::rollup_month_series`):
    - `GET /summary/history?months=N` — the last N months of income/spend/net, oldest first
      (one `rollup_month` per calendar month, zeros for empty months → a dense chart series).
    - `GET /summary/categories?month=` — `rollup_by_category` exposed directly (was only
      reachable through budget actuals), joined with names, largest spend first.
    - `GET /summary/merchants?month=&category_id=&limit=` — the drill-down below category,
      aggregated in SQL (never loads a backfill month into Python, F14 discipline).
    - `GET /summary/safe-to-spend` — the genre's headline number: depository balances minus
      the bills due before the next paycheck (composed from the existing account-balance and
      `/cashflow` services — cards excluded, since a card balance is money owed).
    **Still to do:** the Android chart screens that consume these (#13–#16).
12a. **"Safe to spend" on Home — DONE 2026-07-09.** The Home hero now leads with a rolling
    `TickerNumber` "SAFE TO SPEND $740" (the genre's iconic number — Simple bank's identity),
    fed by `GET /summary/safe-to-spend` (best-effort in `HomeViewModel`, degrades to the status
    line if it hiccups). The whole hero is tappable through to the cash-flow calendar, where the
    "due before payday" breakdown behind the figure lives. This also satisfies #13's hero-ticker
    half. Home baselines re-recorded + eyeballed (the number settles to $740, not a mid-animation
    $0).
12b. **Offline read cache** — today the only offline surface is the cash-entry queue (no read
    cache, unlike Cookbook), and Magpie is tailnet-only, so any moment the phone is off the
    tailnet the app shows *nothing* — a habit-killer for a product whose core law is a
    ten-second daily review. Cache the last-known transactions + month summary + safe-to-spend
    (Room, Cookbook's read-cache precedent) so the app opens to stale-but-real data and
    refreshes when reachable. Small, and it removes the one way the daily habit silently breaks.
13. **Home: numbers that move — DONE 2026-07-09.** Hero `TickerNumber` on the safe-to-spend
    figure (#12a), and the month panel's three tiles (Income/Spend/Net) each carry a 6-month
    `Sparkline` under the value (`GET /summary/history`, best-effort; spend uses magnitudes so the
    line reads "how much", income/net signed). Values still fit their 1/3-width columns (the #30
    single-line pin + #35 AutoFitValue hold). Home baselines re-recorded + eyeballed.
14. **Trends screen — DONE 2026-07-09.** `ui/trends/` (`TrendsScreen` + pure, screenshot-tested
    `TrendsContent` + `TrendsViewModel`), Spotter's `ProgressScreen` analog: a net headline over a
    filled 6-month `Sparkline`, an Income/Spend dense-`StatTile` row each with its own sparkline
    (income green, spend neutral per #31), the current month's category breakdown as proportional
    bars, and the top merchants. Reached from Home as a secondary link (added alongside
    Accounts/Rules); designed empty + error states; light+dark Roborazzi baselines. `assembleDebug`
    + `testDebugUnitTest` green. **Deferred:** tap-a-category → its own monthly trend drill-down
    (folds into #16); Magpie uses Pulse's `Sparkline` rather than a bespoke Canvas, matching the
    dense-tile idiom the siblings actually ship.
15. **Budgets: a ring where it earns it — DONE 2026-07-09.** A `BudgetsRingHeader` tops the list:
    an overall month-utilization `ProgressRing` (total spent / total budget, e.g. "74% · $707 of
    $950 · $243 left"), teal normally and red only when the household is genuinely over its combined
    budget (#31 grammar — the ring carries the alarm, not every row). Rows keep their linear bars.
    Baselines re-recorded + eyeballed.
16. **Merchant view:** tap a merchant anywhere → its history, total, average, and cadence if
    a rule knows it. Cheap — the search/filter plumbing from Tier 4 #32 already exists.

## Wave 2 — The AI wakes up (needs Wave 0's backfill to be worth anything)

Magpie has the suite's richest structured data and its least AI: category drafts are built and
guardrail-tested but the production LLM has never fired, and "first insights" (the pitch's
other half, CLAUDE.md §1.6) were never built at all. The siblings set the bar — Spotter
extracts structured plan/program drafts from conversation; Plate has coach chat and photo
vision. Guardrails unchanged (§6): local model only, DB-derived context (never raw emails),
Pydantic-validated, drafts never auto-commit, descriptive never advisory.

17. **Turn it on.** `[H]`-adjacent: set `llm_base_url` to the live LM Studio, verify category
    -draft quality against real post-backfill data, tune the prompt if needed. Category
    drafts are the review queue's third stage and may not slip.
18. **Monthly insight note** — the unbuilt pitch feature. An LLM-written "what changed"
    (top category deltas vs the trailing median, new recurrences, budget verdicts) generated
    from Wave 1's read models — aggregates in, prose out, never raw rows. Surfaced as a Home
    card in the violet AI voice + an ntfy digest ping. Draft-visible in-app first; insights
    may slip without blocking anything else, category drafts may not (unchanged from V1).
19. **Alert narration:** deviation alerts optionally carry one LLM-drafted context line
    ("XCEL is $31 over its 12-month median; the last outlier was January") appended to the
    ntfy body — never replacing the deterministic fact, which stays first.
19a. **Spending-anomaly alerts** — the *proactive* half of "AI monitoring" the current sweeps
    miss. Today's sweeps catch known deviations (bill missing, paycheck late, account stale);
    nothing catches the novel one — a large charge at a never-seen merchant, or a category
    running well over its trailing median mid-month. New latched sweep(s) on Wave 1's read
    models: same `alert_latches` + fake-clock machinery, deterministic thresholds first
    (an LLM narration line is optional per #19, never the trigger). This is what people
    actually mean by "watch my spending."
20. **Auto-budget proposals — deterministic, not AI:** "Set budgets from your history" offers
    the trailing-3-month median per category as drafts the user confirms one by one. Genre
    table stakes, and it's the review-not-enter law applied to budgets.
21. **Ask-your-ledger chat (owner's go/no-go before building).** The Plate `coach_chat` shape
    over money: a server-side prompt carrying the month's aggregates + category/merchant
    rollups, read-only, descriptive-only, no tool access. Two suite chat precedents exist and
    this is the highest-leverage surface an app like this can have ("how much did we spend on
    dining versus May?") — but it is also the largest new AI surface and the one most
    tempting to over-scope, so it gets an explicit decision, not a default yes.

## Wave 3 — The money works for you

22. **Subscription surfacing** (promoted from post-v1 #1 — it's nearly free). Invert the
    rules engine: a "your recurrences, totaled, sorted by annual cost" screen, plus a
    **new-recurrence-detected** sweep alert ("new monthly charge: $14.99 — HULU") and a
    **price-hike** alert (an upward band breach on a subscription-shaped rule; "Netflix went
    up $3"). The single most actionable screen in consumer finance.
23. **Savings goals:** named buckets funded from the monthly surplus the ledger already
    computes — a `goals` table, a Home card, a progress ring (Wave 1's components).
24. **Cash-flow calendar, projected:** recurring-*bill* rules project into the upcoming set
    (today the calendar shows concrete `bill_statements` only, so it goes blank between
    statement emails) — deferred from V1 Tier 3 #23.
25. **Rule → history application:** creating or editing a merchant rule offers "apply to N
    existing matches" — the replay tool's UI-facing cousin and F15's second customer.
26. **Monthly export/report:** `GET /export/transactions.csv?month=` + a share action. A
    trust feature at near-zero cost: the escape hatch that keeps the data the owner's.
27. **Cross-app wave** (per `Dragonfly/CROSS-APP.md`: flag-gated, degrade-to-absence,
    contract fixtures): Cookbook grocery actuals ("planned vs spent"); the suite weekly
    digest's money paragraph via `GET /cross-app/summary?start=&end=` — RS256 cross-app
    tokens only (Magpie post-dates the HS256 retirement).
28. **Household second user** — second suite account sees shared accounts. Defer exactly as
    Cookbook deferred sharing; SSO-by-email is the identity foundation when it comes.
29. **CSV import polish:** a new-institution mapping wizard (column-guess + preview) once the
    third hand-written mapping happens — unchanged from the original post-v1 list.

### Candidates (weighed, not yet committed — decide when the wave is reached)

- **Home-screen widget** — net-this-month + safe-to-spend + next bill, glanceable without
  opening the app. No suite precedent (a reason for caution, not a veto), but this is the one
  suite app whose headline data is genuinely glance-and-go, and it reinforces the daily-review
  habit. Reconsider once Wave 1's read models + safe-to-spend exist (it would just render them).
- **Budget rollover / envelopes** — budgets are fixed monthly with no carryover, and the
  budget view doesn't separate fixed bills from discretionary spend. Both are real product
  decisions the plan is otherwise silent on; build only if the flat monthly model proves
  frustrating in real use (Wave 0's backfill is the first honest test of that).

## Tier C trigger — when to build the SimpleFIN Bridge integration (unchanged)

Build the read-only aggregator tier **only if**, after a full month of live use, any of:
1. An issuer's alerts prove structurally incomplete (e.g., an issuer only alerts
   card-not-present) *and* that account is >10% of monthly transaction volume — CSV-only
   for a high-traffic account means the ledger is stale 29 days a month.
2. Parser template maintenance exceeds ~1 breakage/month sustained (issuers redesigning
   alert emails faster than they're worth chasing).
3. A needed account type has no alert path at all (some credit unions, HSAs).

Design is pre-made: read-only token in `server/.env`, a `simplefin` source alongside
`email`/`csv` in the same dedupe/matching pipeline, no schema change expected. The
**read-only invariant is non-negotiable** regardless of tier. Note the standing watch items:
Discover's email coverage and the undecided Visa (Wave 0 #2) are the accounts most likely to
trip trigger 1 — the coverage matrix below is how we'd know.

**Coverage matrix (owed during Wave 0's backfill):** one table in ARCHITECTURE.md — per
account: email alerts? CSV? paycheck path? — checked against these triggers.

## Explicitly not worth it (unchanged, owner-locked — pre-empting scope pressure)

- **Plaid or any credential-storing aggregation** — permanently out; the read-only invariant
  is the app's security identity. SimpleFIN (read-only by design) is the only sanctioned tier.
- **Investments / net worth / brokerage tracking** — different problem domain (positions,
  cost basis, market data feeds), different failure modes, and brokerages have real apps.
  Cash flow is the pillar; don't dilute it.
- **Credit score** — requires exactly the bureaus/aggregators this app exists to avoid.
- **Gross pay / withholding / tax anything** — net cash flow only (locked in CLAUDE.md §2).
- **Bill *pay*** — Magpie observes money movement, it never initiates it. This is the
  read-only invariant's product face; rejecting it keeps the threat model honest.
- **Receipt-level line-item OCR as a core loop** — the vision pipeline exists (Plate/
  Cookbook precedent) and could split a grocery receipt someday, but per-line itemization
  is the manual-entry death spiral wearing an AI costume. Transactions are the atom.
  (Transaction *splits* — shipped — cover the honest 90% case by hand.)
- **Multi-currency** — single-household, USD. Revisit never, probably.

## Document map

| Doc | Role |
|---|---|
| CLAUDE.md | Spec, locked decisions, guardrails — authoritative for *rules* |
| ARCHITECTURE.md | As-built system description — authoritative for *what exists* |
| V1.md | Historical record of the 2026-07-05→09 tier build (F1–F18) — closed |
| **ROADMAP.md (this file)** | **The only forward plan** — Waves 0–3 + triggers + non-goals |
