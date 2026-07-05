# ROADMAP.md — Magpie (drafted at spec time, 2026-07-04)

Unusual among the suite's roadmaps: written **before** v1 exists. [CLAUDE.md](CLAUDE.md) owns
the v1 build phases; this file holds what comes *after* v1, the trigger conditions for the
deferred ingestion tier, and the non-goals — so scope pressure during the build has a
written answer.

## Preconditions & immediate actions (blocking items tracked in host ROADMAP2)

- **START NOW (zero code): Phase −1 corpus collection** — turn on per-transaction /
  deposit / withdrawal alerts on all four accounts + the Gmail `magpie-ingest` label +
  biller "statement ready" emails (CLAUDE.md §10 Phase −1). Every week before the build
  starts is free parser corpus and free per-issuer coverage proof.
- **Encrypted NAS dumps** (ROADMAP2 Tier 1 #10) before real financial data enters the DB.
- Magpie's DB joins the nightly backup + restore-drill set (`Backup-DragonflyDatabases.ps1`
  covers `*-db-1` containers generically — verify it picks up `magpie-db-1`, don't assume).
- dragonfly-id gains client `magpie`; hub gains registry + ServiceRegistry + **config-broker
  (`config/magpie`)** entries (Phase 8).
- **`Test-SuiteInvariants.ps1` needs a per-app exception list** before Magpie's first
  deploy — it asserts `COMPOSE_PROFILES=tunnel` suite-wide, which Magpie legitimately
  violates (tailnet-only, no tunnel). Plus its positive checks: runner service, `.env` ACL,
  `tailscale serve status` mapping present. uptime-kuma gets a loopback `/health` monitor.

## Tier C trigger — when to build the SimpleFIN Bridge integration

Build the read-only aggregator tier **only if**, after a full month of live use, any of:
1. An issuer's alerts prove structurally incomplete (e.g., the Visa's issuer only alerts
   card-not-present) *and* that account is >10% of monthly transaction volume — CSV-only
   for a high-traffic account means the ledger is stale 29 days a month.
2. Parser template maintenance exceeds ~1 breakage/month sustained (issuers redesigning
   alert emails faster than they're worth chasing).
3. A needed account type has no alert path at all (some credit unions, HSAs).
Design is pre-made: read-only token in `server/.env`, a `simplefin` source alongside
`email`/`csv` in the same dedupe/matching pipeline, no schema change expected. The
**read-only invariant is non-negotiable** regardless of tier.

## Post-v1, in value order

1. **Subscription/recurrence surfacing.** The rules engine already knows every recurrence;
   invert it into a "your subscriptions, totaled, sorted by annual cost" view + a
   new-recurrence-detected alert ("Netflix went up $3"; "new monthly charge: $14.99").
   Nearly free given `rules` + history, and it's the single most actionable screen in
   consumer finance.
2. **Cross-app wave** (per `Dragonfly/CROSS-APP.md` rules — flag-gated, degrade to absence,
   contract fixtures):
   - Cookbook grocery actuals: match grocery-category spend against checked-off list
     sessions → "planned vs spent" on the Cookbook side or Magpie side (design when built).
   - Digest range read: `GET /cross-app/summary?start=&end=` for the suite weekly digest
     (money paragraph: in/out/top-deltas). Ride the RS256 cross-app tokens — Magpie should
     never carry the legacy HS256 path (it post-dates the retirement).
3. **Savings goals** — named buckets funded from the monthly surplus the ledger already
   computes. Small model addition (`goals`), high household visibility.
4. **Insight cadence** — a monthly LLM-written "what changed" note (top category deltas,
   new recurrences, budget verdicts) delivered via ntfy/digest. Guardrailed, descriptive,
   draft-visible in-app first.
5. **Household multi-user** — second suite account sees shared accounts. Defer exactly as
   Cookbook deferred sharing; SSO-by-email is the identity foundation when it comes. Until
   then Magpie is single-user like the rest of the suite in practice.
6. **CSV import polish** — new-institution mapping wizard (column-guess + preview) instead
   of hand-written mappings, once the third mapping gets written by hand.

## Explicitly not worth it (pre-empting scope pressure)

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
- **Multi-currency** — single-household, USD. Revisit never, probably.
