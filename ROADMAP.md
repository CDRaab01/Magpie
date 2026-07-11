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
| paycheck-late, paycheck-short | `recurring_income` rules | **0 rules** |
| missing-bill, cash-flow calendar, safe-to-spend | `bill_statements` + `recurring_bill` rules | **0 and 0** |
| projected cashflow (#24) | `recurring_bill` rules | **0 rules** |
| statement parity (the v1 acceptance gate) | `statement_checkpoints` | **0 checkpoints** |

All 399 rules are merchant→category. Nothing pages when a paycheck is late because Magpie has
never been told (or never inferred) what a paycheck looks like. **The single highest-leverage
theme is arming what's built, not building more.**

## Theme 1 — Arm the watchtower (the v1 exit, restated)

1. **Seed recurring-income rules from history.** The ledger already shows BAE SYSTEMS (65
   deposits) and VERANEX (39) as obvious paychecks; `detect_recurrence` already infers cadence
   from history for spend. Build the income analog: propose income rules (matcher, cadence,
   band) from deposit history as **drafts the owner confirms** — the same one-tap promotion shape
   as `/rules/from-confirmed`. This arms paycheck-late, paycheck-short, next-paycheck-date, and
   the real safe-to-spend in one stroke.
2. **Seed recurring-bill rules the same way.** The subscriptions detector already found 55
   recurrences including AMER ELECT PWR, AT T, MAZDA FINANCIAL — those are bills. A "make this a
   bill rule" promotion (cadence + band from history) arms missing-bill and the projected
   calendar. Design note: subscriptions/detected-recurrences and bill rules should converge —
   one detection, two confirmations.
3. **`bill_issued` parser** — blocked on **[H]**: the Discover statement-ready sender address
   (open since 2026-07-08; browser flakiness; don't guess). Without it, `bill_statements` only
   fills via manual POST.
4. **[H] Anchor statement checkpoints and start the parity clock.** Enter each account's stated
   balance from its latest statement (the Accounts screen shows the delta). The v1 acceptance
   gate — two consecutive to-the-penny months — has never started counting.
5. **[H] The two remaining exports:** Savings history before 2025-03-31 (the account predates
   its 69 imported rows), and Amex 2024-06→2024-11 (six statements). The Amex gap is why four
   payments totaling $29k sit as unpaired transfers, and it hides whether Dec-2024/Dec-2025/
   May-2026 payments went to a *different* Amex card (three checking payments have no card leg
   anywhere in the export — resolve which while pulling statements).
6. **Watch items that resolve themselves:** the two $9.99 GOOGLE pendings (auth-hold sweep
   drops any unposted one ~2026-07-13; the July Amex CSV settles the real one); the June digest
   + first-run subscription alerts fire once as the latches initialize.

## Theme 2 — Bugs and bad code (found this session, unfixed)

7. **`import_batches` has no `user_id` and no FK to anything.** The only unscoped table left;
   ~88 of its 119 rows are test residue that cannot be attributed or safely pruned. Migration:
   add nullable `user_id`, backfill via each batch's transactions where unambiguous, scope the
   reads. (The residue cleanup deliberately skipped this table.)
8. **Merchant-variant collapsing.** `MEIJER FORT WAYNE IN` / `MEIJER STORE 138…` /
   `MEIJER EXPRESS 138…` are one merchant to a human and three to `merchant_norm`. This caused a
   large-charge false positive (papered over by raising the threshold to $500 — the roadmap
   note says the honest fix is normalization, and this is it), splits rule coverage, and splits
   subscription detection. Approach: a conservative second normalization pass (strip trailing
   store-number + city/state tokens when a longer-prefix match exists), then one
   `/admin/renormalize` dry-run → apply. The infrastructure for safe recompute already exists.
9. **The mortgage counts twice in Subscriptions** (NSM/Mr. Cooper + Rocket Mortgage, ~$53k/yr
   each — one loan across a servicer transfer). Needs a "same obligation" alias or a dismiss
   (see #12); today the headline annual total is inflated by ~$53k.
10. **Rules the model got wrong, still live** `[H eyes, then one call]`: `WHATNOT INC → Other`
    (408 rows — it's a shopping marketplace), `PAYPAL → Other`, `MONTHLY MAINTENANCE FEE →
    Housing` (a bank fee), `ROCKET LAWYER → Housing` (arguably Legal). Fixing a rule +
    `apply-to-history` re-files its rows in one step.
11. **`alert_latches` grows without bound.** Several sweeps latch on per-row keys
    (`large_new_charge:<txn>`, `price_hike:<merchant>:<amount>`, `paycheck_short:<rule>:<txn>`,
    `monthly_digest:<month>`). Harmless at household scale for years, but it's an append-only
    table with no cleanup — add a sweep-side TTL prune (e.g. resolved latches older than 12
    months) before it's an archaeology dig.
12. **Subscription/anomaly dismissals don't exist.** The detector surfaces weekly gas stops and
    Cash-App-to-a-person as "subscriptions" (honest per spec, noisy per life). Add a
    per-merchant mute ("not a subscription") that both the screen and the two sweep alerts
    respect. Same affordance solves #9's duplicate-mortgage row.
13. **Encoding fragility in the toolchain.** UTF-8 mojibake shipped to the Home screen twice
    this session (em-dashes written through cp1252). Fixed by going ASCII, but add the backstop:
    a lint/CI check that source strings contain no `â€`/replacement-char sequences, so the next
    corrupted write fails the build instead of the screenshot review.
14. **Deprecation debt (small):** `androidx.hilt.navigation.compose.hiltViewModel` is deprecated
    across every screen (moved to `androidx.hilt.lifecycle.viewmodel.compose`); one mechanical
    sweep. **Design debt (small):** Home now stacks hero + month panel + insight + Ask Magpie +
    review queue + upcoming + button row — worth one Tier-4-style pass deciding what earns
    first-screen placement before the next card lands.

## Theme 3 — Client affordances for shipped server features

15. **Export share** — `GET /export/transactions.csv` is live; add the Android share action
    (Settings → "Export month" → share sheet; FileProvider + ACTION_SEND).
16. **Budget proposals UI** — `GET /budgets/proposals` is live; surface "Set budgets from your
    history" in the Budgets screen as confirm-one-by-one drafts (review-not-enter for budgets).
17. **Insight detail view** — the Home card shows the deterministic one-liner; tapping could
    open the full month breakdown with the LLM narrative (`narrative=true`), category deltas,
    and budget verdicts, instead of routing to Trends.
18. **Home-screen widget** (carried candidate, now unblocked): net-this-month + safe-to-spend +
    next bill are all served; a Glance widget reinforces the daily-review habit. Reconsider
    once Theme 1 makes safe-to-spend real (it currently renders without paycheck/bill data).

## Theme 4 — Dragonfly portfolio integrations

Magpie is **absent from CROSS-APP.md** — it consumes suite SSO and SuiteConfig but provides no
surface. Per the cross-app design rules (point-to-point HTTPS, flag-gated, degrade-to-absence,
read-only by preference), in priority order:

19. **`GET /cross-app/summary?start=&end=`** — the suite weekly digest's money paragraph
    (income/spend/net + biggest category move for the window; the insight aggregate already
    computes this). **RS256 cross-app tokens only** — CROSS-APP.md's own migration says new
    surfaces skip HS256, and Magpie post-dates the retirement plan. Registering this surface in
    CROSS-APP.md is part of the work (hub territory, so it's a Dragonfly-repo PR too).
20. **Cookbook grocery actuals** — "planned vs spent": Cookbook asks Magpie for the Groceries
    category's month-to-date actual to sit beside its planned grocery spend. Read-only, tiny
    payload, the named use case from the old #27. Depends on #19's auth plumbing.
21. **Hub Suite tile upgrade** — Dragonfly's Magpie tile shows alive/dead today; the summary
    endpoint (#19) lets it show net-this-month like Spotter's tile shows last-workout.
    (Candidate, not committed — hub design is Dragonfly-repo territory.)
22. **Hawksnest home-costs view** (speculative candidate, decide when Hawksnest wants it):
    Housing-category actuals by month over cross-app, so the home app can put utility/maintenance
    spend next to its device and project data. Same read-only summary shape as #20.

## Theme 5 — Operational loose ends (mostly [H], unchanged in substance)

23. **[H] On-device batch:** formal SSO sign-in confirmation, split-sheet interaction, encrypted
    token store (F17), tap one real alert deep link, font-scale/TalkBack pass, eyeball the
    (now ~36) Roborazzi baselines.
24. **[H] Ops:** verify the uptime-kuma monitor exists and pages; backup passphrase → password
    manager + offsite copy; update host `C:\Code\CLAUDE.md` + ROADMAP2's Magpie rows to "live".
25. **Coverage matrix** (owed to ARCHITECTURE.md): per account — email alerts? CSV cadence?
    paycheck path? — checked against the Tier C triggers below.
26. **Alert-narration rollout** (#19 shipped on category-overspend only): thread the optional
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
a third hand-written institution mapping); ask-anything beyond descriptive finance (the chat's
§6 scope is a feature, not a limitation).
