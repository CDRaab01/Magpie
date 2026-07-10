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
matches `main`). Every 2026-07-05 code-review finding is now closed — the last two, F13
(bill-matching guards) and F15 (parser replay), landed 2026-07-09 (#6, #7). Email ingestion is live against the real corpus (Amex / US Bank / Discover parsers);
rules + review queue with corrections and "make this a rule", bills, budgets, cash-flow
calendar, transaction splits, rules editor, onboarding, deep-linked alerts, and the Tier 4
suite-parity pass (bottom bar, hero, content Home, color grammar, ~28 Roborazzi baselines)
have all shipped.

**Superseded 2026-07-09 — all three of the original "But:" gaps are closed.** The ledger now
holds **4,747 real transactions** across four real accounts (Amex, Checking, Savings, Discover),
backfilled from CSV and reconciling; the unparsed ingest backlog is zero. The production LLM is
wired and deployed (`LLM_BASE_URL` + the JSON-fence fix, Wave 2 #17), so the AI categorization
stage fires for real. And Wave 1's charts have landed (Trends, Home sparklines + safe-to-spend
ticker, Budgets ring, merchant drill-down). What remains is proof over time, not absence:
statement parity for two consecutive months (#3), the Savings backfill (#2), and the two
unbuilt sweeps (#5).

## Wave 0 — v1 exit: prove it on real money

**The critical path is data, not code.** The gate chain below is strictly ordered; everything
else in this wave can run in parallel with it.

1. **[H] Create the real accounts — DONE.** Amex (…2005), Checking (…7197), Savings (…6340),
   Discover. **Consolidated 2026-07-09:** a stale second Amex account (…1007, the owner's
   *replaced* card) held one email-sourced charge and no history — a live double-count risk,
   since reconciliation matches within an account and the Amex CSV lands on …2005. Its rows were
   moved to …2005 and the account deleted; `match_account` now also ignores inactive accounts,
   so a retired card's alerts surface in the unparsed operator view rather than misfiling.
   _(Surfaced by that consolidation, still owed to the review queue **[H]**: two $9.99 `GOOGLE`
   pendings a day apart — distinct Message-IDs, one per card number. Either two subscriptions or
   Google re-billing the new card. The July Amex CSV settles it.)_
2. **CSV backfill** per account. **Amex IN HAND + first reality-fix landed (2026-07-09):** the
   owner supplied 16 Amex exports = a complete **18-month** run (2024-12-09 → 2026-06-12, 2633
   rows, one card account). Dry-running the *real* import service against them surfaced the
   expected reality-fix: sign alone is wrong for a card — the naive `amount>0 ⇒ income` would have
   booked **~$208k of phantom income** (17 card payments + 49 refunds). Fixed with
   `institution_mappings.default_kind_for` (card: positive = payment→transfer / refund, never
   income); re-verified on the corpus ($0 income, −$198k net spend, transfers excluded). The fix
   is deployed and the real prod import is done. **US Bank Checking + Savings
   format VALIDATED (2026-07-09):** parses with no code change (standard signed
   format, "Name" = description, no flip); paychecks book as income; the Amex/Discover payment legs
   pair to zero cross-account; and a new fix books internal checking↔savings moves as transfers
   (they were double-counted as spend+income).
   **Backfill status as actually imported (verified against prod 2026-07-09):**
   Amex …2005 — 2,633 CSV rows, 2024-12-09 → 2026-06-12. Discover — 693 rows, 2024-07 → 2026-06.
   **Checking …7197 — 1,317 rows, 2024-06-21 → 2026-07-08, dense and gapless (40–78 rows every
   month): complete, nothing owed.** **Savings …6340 — 69 rows but only from 2025-03-31, and the
   account predates that (owner-confirmed): the full Savings export is the one remaining backfill
   `[H]`.** **Visa: moot** — the "VISA" lines in checking are
   *debit-card* purchases already captured in the checking feed, not a separate credit card.
   **Discover IN HAND + confirmed (2026-07-09):** a real 24-month export (693 rows, 2024-07 →
   2026-06); same positive-is-charge convention as Amex (added to the sign-flip list), and its two
   date columns ("Trans. Date"/"Post Date") needed new parser aliases or the import failed outright.
   Scratch-imported clean: $0 income, 23 payments excluded as transfers, −$18,867 net over 24
   months. The backfill seeds the
   rules engine's medians (cold start §5) and is the precondition for Wave 2's AI being worth
   anything. _(Nice-to-have surfaced: a per-transaction "tag" for the Christian/Elizabeth
   cardholder split — a small future feature, not blocking.)_
2a. **The first real review-queue correction (2026-07-09).** Replay filed a $12,086.78 checking
   outflow as a pending *spend*; the owner identified it as a card payment, and it was confirmed
   as `kind=transfer` through the app's own PATCH path. July spend fell from ~$22.8k to
   $10,729.67 — the concrete proof of the double-count law (CLAUDE.md §2: card payments are
   transfers, never spend). It sits **unpaired** (`transfer_group` NULL) until the July Amex CSV
   imports its other leg; note F3 then routes that leg to review rather than auto-pairing,
   because this row is now human-`confirmed` and must never be silently rewritten. Pairing it is
   a one-tap `[H]` follow-up once the Amex July export lands.
3. **[H] Anchor checkpoints and drive every account to "Reconciled"** — then the
   **statement-parity clock starts**: two consecutive to-the-penny months (§9, the v1
   acceptance gate). Mostly elapsed time plus a monthly reconciliation habit.
4. **[H] Paycheck path:** confirm whether US Bank deposit alerts actually arrive by email
   (the parser already handles "deposit of" if so); if not, document that paycheck detection
   is CSV-only and the recurring-income rule keys off history alone.

Code items, all unblocked now:

5. **The two remaining sweeps.** **Auth-hold expiry — DONE 2026-07-10** (`run_auth_hold_expiry_
   sweep`, wired into `sweep_loop`): a pending **card** auth >7 days with no posted match drops
   with an audit note. The row is *kept* (`status="expired"` + `rule_note`), never deleted, and
   `COUNTABLE_STATUSES` is now the single filter balances/rollups/budgets/summaries share, so an
   expired hold stops being money in exactly one place. It refuses to touch a human-confirmed row,
   a paired transfer leg, or a hold with a posted match (`find_posted_duplicate` — the same
   tolerance the importer and replay use, so all three agree, settled tips included). **Scoped to
   card accounts after dry-running against the live ledger:** a depository "pending" is a real
   completed ACH debit awaiting CSV import (a $193.47 checking row sat exactly in that trap), and
   expiring those would silently delete real activity whenever a reconciliation import slipped a
   week. No ntfy alert — an expiring $1 pre-auth is routine, and paging for routine is how alerting
   dies. 12 time-travel tests. **Paycheck-short — DONE 2026-07-10** (`run_paycheck_short_sweep`):
   pages once, with median context, when a recurring-income rule's *most recent* paycheck lands
   below its band (arrived-but-light, vs paycheck-late's never-arrived). Built as a **sweep**, not
   the ingestion hook the earlier note guessed at — detecting from ledger state reuses the latch +
   publisher and, by only inspecting the latest observation per rule, can't storm the phone with
   past short weeks during a backfill (the ingestion hook's failure mode). `band_shortfall` is
   directional: a *high* paycheck is out of band too but is deliberately silent. **Both sweeps are
   now built; the sweep set is complete.**
6. **Bill-matching guards (F13) — DONE 2026-07-09.** The matcher compared `abs(amount)` alone,
   so a same-magnitude *deposit* near the due date "paid" the bill and silenced its missing-bill
   alert — strictly worse than a bill that looks unpaid. Now a payment must be an outflow of a
   payment-shaped kind (`spend`/`transfer`; a card statement paid from checking is a transfer
   leg). One bill per transaction is enforced twice: `bill_service._find_payment` excludes
   already-claimed transactions, and a partial unique index on
   `bill_statements.matched_transaction_id` (migration `a1d4c7e2b905`) is the durable backstop.
   The pool is now narrowed in SQL rather than loading the whole account into Python (F14).
   13 pure + 9 service tests, including one that proves the index itself rejects a duplicate
   claim. No violations existed in prod, so the index applies cleanly.
7. **Parser replay tool (F15) — DONE 2026-07-09**, then the `bill_issued` parser.
   `app/services/replay_service.py` + `POST /ingest/replay` re-parse the `unparsed` backlog with
   today's parsers and file what now fits, through the same `evaluate_transaction` path a live poll
   uses. `dry_run=true` is the default (it runs the real path and rolls back, so the report is
   honest); replay is idempotent; and it will not double-count the backfill — a replayed alert
   whose swipe the CSV already posted is recorded `duplicate` via `find_posted_duplicate()`, the
   inverse of the F4 matcher, reusing its one "same swipe" tolerance. Scoped to `unparsed` events
   on purpose: re-parsing a `created` one mutates live history and belongs with #25. 11 tests
   (service + endpoint) and 7 more on the pure matcher. **Run against prod 2026-07-09 and its
   customer is served:** the "22 unfiled Amex alerts" this item was written for had already
   auto-filed once the real Amex account existed; the actual backlog was 4 US Bank events, of
   which 2 filed and **2 were correctly refused as swipes the CSV backfill had already posted** —
   the double-count guard earning its keep on real money. The unparsed backlog is now zero. The
   Discover
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
11. **Ops loose ends:** verify the uptime-kuma monitor exists and pages; update host
    `C:\Code\CLAUDE.md` + ROADMAP2's Magpie rows from "planned" to live; backup passphrase →
    password manager + offsite copy **[H]**.
11a. **`pytest` wrote into the production database — fixed at the source AND cleaned up
    2026-07-09.** `app/config.py` falls back to `server/.env` when `DATABASE_URL`
    is unset, and on this host that file points at the live `magpie` DB on :5436. CI was safe
    only by accident (its workflow exports `.../magpie_test`); a bare local `pytest` resolved to
    prod. This is the real, much larger story behind the old "smoke user's prod residue" line:
    **456 of 458 users, ~402 of 408 accounts and 464 transactions in prod are test residue**
    (last4 `0000`/`9999`, `@magpie.test` emails), accumulated over the build. *Fixed:* `tests/
    conftest.py` now pins the database name to `*_test` before `app.*` is imported, with a
    tripwire that refuses a non-`_test` target; verified by running the full suite and watching
    the prod user count hold at 458. **The real financial data was never corrupted** — the 2 real
    users, 6 real accounts and 4,745 real transactions are untouched (every service is
    user-scoped, so test rows never mingled). *Cleaned up:* `scripts/cleanup_test_residue.sql`
    (rehearsed on a restored dump both ways — correct run, and an injected over-broad pattern that
    the tripwire aborted) was applied to prod: `DELETE 456`, "OK: 4745 real transactions
    preserved", ending at 2 users / 6 accounts, zero orphans. A second bug hid behind the first —
    CI runs `alembic upgrade head` before pytest and nothing did locally, so the suite had been
    leaning on prod's migrated schema; conftest now runs alembic itself. *Still owed:*
    `import_batches` has no `user_id` and no FK to one, so ~88 test batches there can't be
    attributed or pruned — scoping that table to a user is the real fix, not a DELETE.

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
16. **Merchant view — DONE 2026-07-09.** `ui/merchant/` (`MerchantDetailScreen` + pure
    `MerchantDetailContent` + `MerchantDetailViewModel`): tap a merchant in Trends → its full
    history, with a summary card (total spent, transaction count, average ticket) over the row
    list. Loads via the existing `q` merchant search (Tier 4 #32 plumbing — no new endpoint),
    filtered to spend/refund so a same-named income row can't skew the average; light+dark
    Roborazzi baselines. **Deferred:** tapping a *category* → its merchants (the category→merchant
    hop); showing a merchant's rule cadence when one exists.

## Wave 2 — The AI wakes up (needs Wave 0's backfill to be worth anything)

Magpie has the suite's richest structured data and its least AI: category drafts are built and
guardrail-tested but the production LLM has never fired, and "first insights" (the pitch's
other half, CLAUDE.md §1.6) were never built at all. The siblings set the bar — Spotter
extracts structured plan/program drafts from conversation; Plate has coach chat and photo
vision. Guardrails unchanged (§6): local model only, DB-derived context (never raw emails),
Pydantic-validated, drafts never auto-commit, descriptive never advisory.

17. **Turn it on.** **LIVE-PROBED 2026-07-09 against the suite's `google/gemma-4-e4b`** (the
    model Spotter/Plate use, served by LM Studio on `:1234`). Two findings: (a) **a real bug the
    fake-client tests hid** — gemma wraps its JSON in a ```json … ``` markdown fence even when
    told "only JSON", so `model_validate_json` dropped **every** suggestion (0/12) in production
    while CI stayed green; **fixed** (`_extract_json_object` strips the fence / takes the outermost
    `{...}`, + 3 regression tests using the real reply shape). (b) **Quality is good** — after the
    fix, 11/12 matched the obvious category, the 1 "miss" defensible (MEIJER→Shopping for a
    superstore), 0 parse failures, ~3.7 s/draft (fine for a background review-queue suggestion).
    **Config wired 2026-07-09:** `LLM_BASE_URL` (`http://host.docker.internal:1234`, verified
    reachable from the container) + `LLM_MODEL` (`google/gemma-4-e4b`) are in the compose
    `environment:` block (invariant #4; overridable via the host root `.env`), so the stage is
    **on by default once deployed**. Also hardened the call for going live: `suggest_category` now
    swallows *any* client failure (unreachable/slow LM Studio, HTTP error, odd response shape) →
    no draft, never an exception into the poll loop (it only caught parse errors before; the
    call site in `rule_service` doesn't guard it) — a model hiccup must never break ingestion.
    **The one remaining step is the deploy `[H]`:** the running prod container is `main`'s image,
    which lacks the fence fix — so this config only helps once the server is deployed *with* the
    fence fix (both live on this branch). Deploying = getting this branch onto `main` (CI deploys
    the server; note the branch also carries `android/**`, so it cuts an APK release too) — the
    owner's merge/deploy call. After deploy, re-verify draft quality on real post-backfill merchants.
17a. **The AI ran over the whole backfill (2026-07-10).** 1,265 distinct merchants classified by
    `gemma-4-e4b` in ~13 min (batched 20/call, ids not echoed merchant strings, so a paraphrased
    name cannot mis-assign a row), **0 parse failures**, producing 4,127 `ai_suggested_category_id`
    **drafts**. `category_id` was never written — the guardrail held under bulk load.
    **The run's real payoff was a correctness bug, not the labels:** the model kept filing the
    largest "merchants" as `Other`, because they were not merchants — they were card payments
    booked as `spend` ($89k across three buckets). That produced the transfer-window fix and the
    reclassification above (#2a). Vocabulary gaps then showed up as a $69k `Other` bucket;
    adding **`Education`** and **`Taxes`** (user-scoped, like `Debt Payment`) and re-drafting only
    the `Other` merchants cut it to $42k, with $18.2k landing in `Taxes`.
    **Owed:** an **`Insurance`** category ($5.7k of GEICO/SAFECO still in `Other`), and the honest
    ceiling of name-only classification — `PB CANTERBURY S FORT WAYNE IN` stayed `Other` even with
    `Education` available. Merchant *rules* (§5 step 4), not re-prompting, are the fix: ~200
    approvals cover 84% of spend, vs 4,127 individual confirmations.
18. **Monthly insight note — DONE server-side 2026-07-10** (`insight_service` +
    `app/services/ai/insight.py` + `GET /insights/monthly?month=` + `run_monthly_digest_sweep`).
    The deterministic aggregate (income/spend/net, per-category this-month-vs-trailing-median
    deltas, over-budget verdicts, top merchants) is the source of truth, aggregated in SQL (F14),
    verified against the real ledger (June nets $15,927; deltas + merchants legible). The LLM
    narrates those aggregates under §6 — DB-derived figures only, Pydantic-validated
    `{headline, summary}`, best-effort — and a garbled/absent model degrades to aggregates-only;
    a test asserts the prompt carries rounded dollars, never raw cents. The ntfy digest fires a
    one-line recap once per completed month (latched), LLM headline when up, a deterministic
    spend/net + biggest-mover line when not. **Home insight card DONE 2026-07-10** (client): a
    violet `PanelCard` under "This month" showing the LLM headline+summary when present, else a
    deterministic biggest-mover line ("Dining is running $400 over its usual"), hiding itself when
    nothing's notable; taps through to Trends. A new `aiVoice` (Pulse Violet) channel makes "the
    model said this" read at a glance. Home fetches with `narrative=false` so it never waits on the
    LLM (the prose lane is the digest). Home baselines re-recorded + eyeballed, light+dark.
    **#18 is now complete end-to-end.** Earlier prototype notes retained below for context.
    _Original description follows._ An LLM-written "what changed"
    (top category deltas vs the trailing median, new recurrences, budget verdicts) generated
    from Wave 1's read models — aggregates in, prose out, never raw rows. Surfaced as a Home
    card in the violet AI voice + an ntfy digest ping. Draft-visible in-app first; insights
    may slip without blocking anything else, category drafts may not (unchanged from V1).
19. **Alert narration:** deviation alerts optionally carry one LLM-drafted context line
    ("XCEL is $31 over its 12-month median; the last outlier was January") appended to the
    ntfy body — never replacing the deterministic fact, which stays first.
19a. **Spending-anomaly alerts — DONE 2026-07-10** (`run_large_charge_sweep` +
    `run_category_overspend_sweep`). Two deterministic triggers, both latched, both fake-clock
    tested: (1) a large charge (≥$500) at a merchant *never seen before*, recency-windowed so a
    backfill doesn't storm the phone; (2) a category whose month-to-date spend runs over 1.5× its
    trailing full-month median (with an absolute floor and a ≥3-prior-month bar). The numeric
    judgments are pure (`app/rules/anomaly.py`); the SQL aggregates per (category, month) rather
    than loading rows (F14). **Tuned against the live ledger before trusting it:** a read-only
    pass caught two would-be false positives — a $232 Meijer grocery run flagged "new" only
    because `MEIJER FORT WAYNE IN`/`MEIJER STORE 138…` normalize apart (raised the bar $200→$500),
    and a nameless US Bank "transaction complete" debit (skip empty merchant names). Category-
    overspend was already quiet (mid-month, everything under median). LLM narration (#19) is still
    optional and never the trigger. **Watch item:** merchant-string variants (the Meijer case) can
    still trip trigger 1 above $500 — the deeper fix is better `merchant_norm` collapsing, not a
    higher threshold.
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
25. **Rule → history application — DONE 2026-07-10** (server side). `POST /rules/from-suggestions`
    promotes each merchant's AI draft into a deterministic `merchant_category` rule and files its
    whole history; `POST /rules/{id}/apply-to-history` does it for one existing rule. Both default
    to `dry_run=true`. **Calling the endpoint is the human confirmation §6 requires** — afterwards
    the model is out of the loop for that merchant and the rule explains itself ("matched rule:
    THERESA"). Applied to prod at `min_transactions=2`: **373 rules filed 3,192 transactions, and
    the review queue fell 4,368 → 1,176.** Guards: a rule never overrules a human (a merchant with
    *any* confirmed row gets no rule — a bug the prod dry run caught, where GOOGLE's 5 confirmed
    rows carried no AI draft and were invisible to the per-group check); a merchant whose rows
    disagree on the draft is skipped, never guessed; income rows never inherit a spend category;
    re-running is idempotent. Matching reuses `merchant_match.matches`, never a SQL `LIKE`, so a
    rule cannot mean one thing at ingest and another applied to history.
    **Still owed:** the Android affordance (this is server-only), and three rules the model got
    wrong that want an owner's eye — `MONTHLY MAINTENANCE FEE → Housing` (a bank fee),
    `WHATNOT INC → Other` (408 rows, a shopping marketplace), `PAYPAL → Other`.
25a. **`merchant_norm` was stale everywhere, and Zelle payees were unmatchable — fixed
    2026-07-10.** Two bugs. (a) The backfill imported 4,712 rows *before* the bank-prefix
    stripping was deployed, so every stored `merchant_norm` was computed by an older normalizer
    (`WEB AUTHORIZED PMT VENMO` never became `VENMO`). (b) Zelle carries a per-transaction
    confirmation reference inside the merchant string, so each payment normalized to its own
    merchant — 127 "merchants" for 27 real counterparties, and **no rule could ever match a Zelle
    payee**. The naive fix (strip any long trailing token) is not idempotent and eats surnames
    (`JOSE HANDYMAN → JOSE`); the reference is instead recognized as long *and* machine-shaped
    (bank-code prefix, or contains a digit), with a ≥2-token guard. Re-normalizing 1,186 rows
    collapsed 1,365 → 1,250 distinct merchants and surfaced real recurring payees (THERESA ×31 =
    $15,156; JOSE HANDYMAN ×6). Verified idempotent on live data: a second pass changed 0 rows.
    **The pattern, now three times over** (parser `parse_version`, the pre-deploy CSV import, and
    now `merchant_norm`): the code was right and the *data* was computed by yesterday's code. A
    `POST /admin/renormalize` — same shape as `/ingest/replay`, dry-run by default — would retire
    the scratch script this needed.
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
