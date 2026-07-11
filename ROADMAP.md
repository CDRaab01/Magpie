# ROADMAP.md — Magpie (rewritten 2026-07-10: the single forward roadmap)

> **This file is the only forward-looking plan.** The previous roadmap (2026-07-09) had decayed
> into a changelog — 23 DONE annotations burying a handful of open items — the exact failure mode
> its own header warned about. The build record lives in git history and the session logs;
> [V1.md](V1.md) and CLAUDE.md §10 hold the original phases; [ARCHITECTURE.md](ARCHITECTURE.md)
> is as-built. Locked decisions (CLAUDE.md §2) and the non-goals at the bottom are unchanged and
> not up for relitigation. `[H]` = needs the owner's hands, credentials, or eyes.

## Where the app actually stands (2026-07-10, verified against prod — not memory)

Every feature wave is built and deployed: the correctness core (F1–F18 all closed), CSV backfill
(4,747 real transactions, 4 accounts), email ingestion (unparsed backlog **zero**), 399
merchant-category rules auto-filing ~73% of history, the AI stack (categorization drafts,
monthly insight + digest, alert narration, ask-your-ledger chat — all §6-guardrailed,
live-probed against gemma), nine latched sweeps, subscriptions/export/auto-budgets/projected
cashflow, and the Android surfaces for all of it. Review queue: 0. 428 server tests green.

**But the watchtower is unarmed.** The sweeps watch rule types and tables that are empty in prod:

| Sweep / feature | Watches | In prod |
|---|---|---|
| paycheck-late, paycheck-short | `recurring_income` rules | **1 rule** (INNAGO; BAE held for leave) |
| missing-bill, cash-flow calendar, safe-to-spend | `bill_statements` + `recurring_bill` rules | **0 statements, 9 rules** |
| projected cashflow (#24) | `recurring_bill` rules | **9 rules** |
| statement parity (the v1 acceptance gate) | `statement_checkpoints` | **0 checkpoints** (manual-entry path now shipped; awaiting `[H]`) |

All 399 rules are merchant→category. Nothing pages when a paycheck is late because Magpie has
never been told (or never inferred) what a paycheck looks like. **The single highest-leverage
theme is arming what's built, not building more.**

## Theme 1 — Arm the watchtower (the v1 exit, restated)

1. **Seed recurring-income rules from history — BUILT + PARTIALLY ARMED 2026-07-10.** Detection
   (`app/rules/income.py`, its own module — a paycheck's *timing* is regular but its *amount*
   swings, so the band is derived from robust spread, unlike subscription detection),
   `income_rule_service` (recency gate + amount floor), `POST /rules/from-income` (dry-run
   default, anchors `last_matched_at` to the latest deposit). Guards verified on real data:
   VERANEX (former employer) excluded by recency, $8 interest/fee credits by the floor,
   person-to-person Venmo by the chaotic-amount guard. **Arming outcome, after a fresh US Bank
   import (2026-07-10, reconciled 2 pending rows to posted, no double-count of the $12k transfer):**
   - **INNAGO (rent) — armed.** Monthly ±15%, anchored 2026-07-08. Sweep dry-run confirmed 0
     false fires.
   - **BAE — held, NOT armed.** It's the owner+wife's *current* dual-earner paycheck (two deposits
     per date), but they're on **parental leave** right now, so BAE pay is paused (last 06-25) —
     arming today would false-fire "late" during a known gap. Arm when leave ends and BAE resumes
     its biweekly rhythm.
   - **LINA NYL — excluded.** Maternity/paternity leave pay — *temporary* income; a permanent rule
     would page "late" the moment leave correctly ends.
   **Two gaps this surfaced:** (a) `/rules/from-income` arms **all** proposals at once; real use
   needs **per-proposal selection** (the owner armed only INNAGO by hand) — the seed should
   return proposals and take a confirm-these-IDs list, like a review queue. (b) The recency gate
   (45d) cannot distinguish a just-ended job / a leave gap from a slightly-late paycheck — the
   owner's judgment is the only backstop, which is exactly why selective confirm (a) matters.
   Still open **[H]:** confirm US Bank *deposit* alerts arrive by email (parser handles "deposit
   of"; live evidence is debits only) — if not, paycheck detection is CSV-cadence-only.
2. **Seed recurring-bill rules the same way — BUILT + ARMED 2026-07-10.** `bill_rule_service`
   shares the `detect_recurring` detector with income; `POST /rules/from-bills` (with selective
   `only=`) proposes bill-shaped spend, binds each rule to its payment rail (account with the most
   charges for that biller, §2), skips the amount floor, and excludes dormant billers by the same
   recency gate (the former-residence Ohio utilities). `run_bill_late_sweep` (latched, → `magpie://
   bills`) pages once per episode when an expected payment doesn't land. Nine live bills armed:
   MAZDA, DEPT EDUCATION, AMER ELECT PWR (band 0.27, seasonal), AT&T, Verizon, GEICO, Fort Wayne
   Utilities, Frontier, NIPSCO (band 0.40). Card payments (BARCLAYCARD) and low-value recurrences
   (coffee, gas, a $2.49 vending machine, Garmin/Plex subs) were deliberately NOT armed — the
   detector finds all recurring spend; only real obligations become rules. Design note still open:
   subscriptions/detected-recurrences and bill rules should converge — one detection, two
   confirmations.
3. **`bill_issued` parser** — blocked on **[H]**: the Discover statement-ready sender address
   (open since 2026-07-08; browser flakiness; don't guess). Without it, `bill_statements` only
   fills via manual POST.
4. **Anchor statement checkpoints and start the parity clock — CODE BUILT 2026-07-10, awaiting
   `[H]` balance entry.** Checkpoints were only created when an imported CSV row carried a balance
   column; none of the owner's exports do (119 imports → 0 checkpoints), and there was **no manual
   entry path** — the original "[H] just enter the balances" instruction was impossible as written
   (caught 2026-07-10). Now built: `POST`/`GET /accounts/{id}/checkpoints` (upsert-by-date, signed
   balances, future-date rejected, ownership-checked; deployed) and an Accounts-screen affordance
   ("Enter statement balance" / "Update balance" per row, opening a date+amount dialog; merged).
   **Remaining `[H]`:** open each account, enter its latest statement's closing balance, then do it
   again next month — the v1 acceptance gate (two consecutive to-the-penny months) starts counting
   only once each account has two checkpoints to reconcile between.
5. **[H] The two remaining exports:** Savings history before 2025-03-31 (the account predates
   its 69 imported rows), and Amex 2024-06→2024-11 (six statements). The Amex gap is why four
   payments totaling $29k sit as unpaired transfers, and it hides whether Dec-2024/Dec-2025/
   May-2026 payments went to a *different* Amex card (three checking payments have no card leg
   anywhere in the export — resolve which while pulling statements).
6. **Watch items that resolve themselves:** the two $9.99 GOOGLE pendings (auth-hold sweep
   drops any unposted one ~2026-07-13; the July Amex CSV settles the real one); the June digest
   + first-run subscription alerts fire once as the latches initialize.

## Theme 2 — Bugs and bad code (found this session, unfixed)

7. **`import_batches` user scoping — DONE 2026-07-11.** Added nullable `user_id` + FK, backfilled
   from each batch's transactions where they resolve to one owner (prod: 20/121 rows attributed;
   the ~101 test-residue rows with no surviving transactions stay NULL), and the import service
   now sets `user_id` on every new batch. It's no longer the one unscoped table.
8. **Merchant-variant collapsing.** `MEIJER FORT WAYNE IN` / `MEIJER STORE 138…` /
   `MEIJER EXPRESS 138…` are one merchant to a human and three to `merchant_norm`. This caused a
   large-charge false positive (papered over by raising the threshold to $500 — the roadmap
   note says the honest fix is normalization, and this is it), splits rule coverage, and splits
   subscription detection. Approach: a conservative second normalization pass (strip trailing
   store-number + city/state tokens when a longer-prefix match exists), then one
   `/admin/renormalize` dry-run → apply. The infrastructure for safe recompute already exists.
9. **The mortgage counts twice in Subscriptions** (NSM/Mr. Cooper + Rocket Mortgage, ~$53k/yr
   each — one loan across a servicer transfer). **#12's mute now gives it a dismiss** (`[H]`:
   tap "Not a subscription" on the stale servicer's row). A true "same obligation" alias is still
   the deeper fix, but the headline total is no longer stuck inflated.
10. **Rules the model got wrong, still live** `[H eyes, then one call]`: `WHATNOT INC → Other`
    (408 rows — it's a shopping marketplace), `PAYPAL → Other`, `MONTHLY MAINTENANCE FEE →
    Housing` (a bank fee), `ROCKET LAWYER → Housing` (arguably Legal). Fixing a rule +
    `apply-to-history` re-files its rows in one step.
11. **`alert_latches` TTL prune — DONE 2026-07-11.** `prune_resolved_latches` (delete inactive
    latches older than 365 days) runs once per sweep loop. Active latches (open conditions) are
    never pruned; a resolved key that recurs re-materializes and fires a correct fresh rising edge.
12. **Subscription/anomaly dismissals — DONE 2026-07-11.** `subscription_mutes` (per-user,
    per-merchant) + `POST`/`DELETE /subscriptions/mute` + `GET /subscriptions/mutes`.
    `list_subscriptions` filters muted merchants, so one mute drops the merchant from the screen
    AND both subscription sweeps. Android: a "Not a subscription" (Block icon) dismiss on each
    recurring row, optimistic with restore-on-failure. Silences the weekly gas stop / person, and
    gives #9's double-counted mortgage its dismiss.
13. **Encoding fragility in the toolchain — GUARD ADDED 2026-07-11.** UTF-8 mojibake shipped to
    the Home screen twice (em-dashes written through cp1252). `scripts/check_encoding.py` (wired
    into CI as the "Encoding guard" job) now scans source for the cp1252-mangle marker sequences
    and the U+FFFD replacement char, so the next corrupted write fails the build instead of the
    screenshot review. (The check caught a literal mojibake example that had been sitting in this
    very roadmap item.)
14. **The chat/insight LLM timeout — DONE (earlier this session).** `llm_timeout_seconds=15` /
    `llm_chat_timeout_seconds=60` are config; `make_llm_client` takes a per-call override and
    `/chat` uses the long one and carries a `20/minute` slowapi limit.
14a. **Projected-bill suppression too broad — DONE 2026-07-11.** `_projected_bills` now only lets a
    concrete statement suppress a projection when it lands within ±15 days of the projected date
    (`PROJECTION_MATCH_WINDOW_DAYS`), so a distant early/late statement no longer hides a projection
    it doesn't cover.
15. **Deprecation debt (small):** `androidx.hilt.navigation.compose.hiltViewModel` is deprecated
    across every screen (moved to `androidx.hilt.lifecycle.viewmodel.compose`); one mechanical
    sweep. **Design debt (small):** Home now stacks hero + month panel + insight + Ask Magpie +
    review queue + upcoming + button row — worth one Tier-4-style pass deciding what earns
    first-screen placement before the next card lands.

## Theme 3 — Client affordances for shipped server features

15a. **Offline read cache — restored; the 2026-07-09 rewrite dropped it while still open.**
    Magpie is tailnet-only, and the only offline surface is the cash-entry queue: off the
    tailnet, the app shows *nothing* — a habit-killer for a ten-second daily review. Cache
    last-known transactions + month summary + safe-to-spend in Room (Cookbook's read-cache
    precedent) so the app opens to stale-but-real data and refreshes when reachable.
15b. **Tier-4 UI leftovers (also dropped while open):** the review queue's AI-suggestion text
    should use the violet `aiVoice` channel now that it exists (only the insight card and chat
    use it); inline editing of a rule's band/cadence (the editor is enable/disable/delete
    today — and Theme 1's seeded income/bill rules make band editing matter); the `flip_sign`
    override checkbox in the import dialog (server param exists). Subscriptions/Chat
    discoverability from Home folds into #15's placement pass.
16. **Export share — DONE 2026-07-11.** Settings has an "Export" section (month field + button)
    that fetches `GET /export/transactions.csv` and hands the CSV to the system share sheet via a
    FileProvider `content://` URI (cache/exports/, ACTION_SEND, no storage permission).
17. **Budget proposals UI — DONE 2026-07-11.** The Budgets screen shows a "Suggested from your
    spending" section (from `GET /budgets/proposals`): one confirm-per-row draft per un-budgeted
    category (trailing-median amount + Set button), review-not-enter. Accepting one creates the
    budget and drops the draft.
18. **Insight detail view** — the Home card shows the deterministic one-liner; tapping could
    open the full month breakdown with the LLM narrative (`narrative=true`), category deltas,
    and budget verdicts, instead of routing to Trends.
19. **Home-screen widget** (carried candidate, now unblocked): net-this-month + safe-to-spend +
    next bill are all served; a Glance widget reinforces the daily-review habit. Reconsider
    once Theme 1 makes safe-to-spend real (it currently renders without paycheck/bill data).

19a. **AI budget coach — SHIPPED 2026-07-11 (owner-requested large feature).** Goals + pace
    awareness + coaching, in four stages, all deployed:
    - **Server core:** `goals` table (one active monthly-savings target), pure `app/rules/pace.py`
      (per-category pace with early/on_track/watch/over_pace/over; income = max(MTD, 3-mo median),
      never extrapolated — leave-adaptive; spend = elapsed-weighted blend; greedy cut planner
      floored at MTD spend, ≤50% cuts, bill-dominated categories untouchable), `GET /coach/status`
      (FULL budget table w/ per-category trailing median + delta-vs-usual + uncategorized MTD),
      `GET /coach/plan`, `GET /coach/category/{id}` (deep-dive: trend/budget history/merchants),
      goal CRUD, `PATCH /budgets/{id}`; carry-forward proposals on month rollover.
    - **Sweeps:** budget-pace nudge (day ≥ 10, $50 floor, latched per category+month, BATCHED into
      one message per run) and savings-goal-risk (latched per month), both → `magpie://budgets`;
      the monthly digest closes the loop with a goal hit/missed + budgets-held verdict.
    - **AI (§6 amendment, owner-approved):** coach + chat may be prescriptive about the household's
      OWN budgets/goal; `ai/coach.py` narrates status/plan/category on `?narrative=true`; chat is
      grounded with the full budget table + goal and advises-never-acts. Insight stays descriptive.
    - **Android:** GoalCard (projection vs goal, "How do I get there?"), pace lines + pace-aware
      channels on budget rows, violet `aiVoice` CoachCard, plan sheet (cuts as one-tap drafts,
      honest shortfall), category analysis sheet (Sparkline + merchants + coach's read),
      uncategorized note, budgets deep link. 502 server tests green.
    `[H]`: update the stale $50 Dining budget (real spend ~$800/mo — the first pace nudge will
    correctly page about it) and set a savings goal to arm the goal sweep.

## Theme 4 — Dragonfly portfolio integrations

Magpie is **absent from CROSS-APP.md** — it consumes suite SSO and SuiteConfig but provides no
surface. Per the cross-app design rules (point-to-point HTTPS, flag-gated, degrade-to-absence,
read-only by preference), in priority order:

20. **`GET /cross-app/summary?start=&end=`** — the suite weekly digest's money paragraph
    (income/spend/net + biggest category move for the window; the insight aggregate already
    computes this). **RS256 cross-app tokens only** — CROSS-APP.md's own migration says new
    surfaces skip HS256, and Magpie post-dates the retirement plan. Registering this surface in
    CROSS-APP.md is part of the work (hub territory, so it's a Dragonfly-repo PR too).
21. **Cookbook grocery actuals** — "planned vs spent": Cookbook asks Magpie for the Groceries
    category's month-to-date actual to sit beside its planned grocery spend. Read-only, tiny
    payload, the named use case from the old #27. Depends on #20's auth plumbing.
22. **Hub Suite tile upgrade** — Dragonfly's Magpie tile shows alive/dead today; the summary
    endpoint (#20) lets it show net-this-month like Spotter's tile shows last-workout.
    (Candidate, not committed — hub design is Dragonfly-repo territory.)
23. **Hawksnest home-costs view** (speculative candidate, decide when Hawksnest wants it):
    Housing-category actuals by month over cross-app, so the home app can put utility/maintenance
    spend next to its device and project data. Same read-only summary shape as #21.

## Theme 5 — Operational loose ends (mostly [H], unchanged in substance)

24. **[H] On-device batch:** formal SSO sign-in confirmation, split-sheet interaction, encrypted
    token store (F17), tap one real alert deep link, font-scale/TalkBack pass, eyeball the
    (now ~36) Roborazzi baselines.
25. **[H] Ops:** verify the uptime-kuma monitor exists and pages; backup passphrase → password
    manager + offsite copy; update host `C:\Code\CLAUDE.md` + ROADMAP2's Magpie rows to "live".
26. **Coverage matrix** (owed to ARCHITECTURE.md): per account — email alerts? CSV cadence?
    paycheck path? — checked against the Tier C triggers below.
27. **Alert-narration rollout** (shipped on category-overspend only): thread the optional
    LLM context line through missing-bill, paycheck-short, and price-hike once narration proves
    its keep on the first one.

## Tier C trigger — SimpleFIN Bridge (unchanged, owner-locked)

Build the read-only aggregator only if, after a full month of live use: an issuer's alerts are
structurally incomplete *and* that account is >10% of volume; or parser maintenance exceeds
~1 breakage/month sustained; or a needed account type has no alert path. Design pre-made:
read-only token in `server/.env`, a `simplefin` source in the same dedupe pipeline. The
**read-only invariant is non-negotiable** regardless of tier.

## Explicitly not worth it (unchanged, owner-locked — pre-empting scope pressure)

Plaid-style credential storage (permanently out); gross-pay/tax decomposition; investment
tracking; multi-currency; receipt OCR; browser extensions; a web UI. **Deferred, not dead:**
household second user (defer exactly as Cookbook deferred sharing); CSV mapping wizard (trigger:
a third hand-written institution mapping); per-transaction cardholder tag (the
Christian/Elizabeth split surfaced during the Amex backfill — small, real, not blocking);
ask-anything beyond descriptive finance (the chat's §6 scope is a feature, not a limitation).
