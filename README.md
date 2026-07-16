# Magpie

Household cash-flow tracking for the Dragonfly suite: automatic capture from transaction-alert
emails + monthly CSV reconciliation, deterministic rules, local-AI category drafts, and a
review-not-enter product law. **Tailnet-only, SSO-only, read-only by construction** — nothing
in this system can move money.

What it does today:

- **Automatic capture + reconciliation** — Amex / US Bank / Discover alert-email parsing, monthly
  CSV import with per-institution sign conventions, pending→posted matching, balance anchoring.
- **Deterministic rules + review queue** — recurring income/bills with tolerance bands, transfer
  pairing, merchant→category rules; the local LLM drafts the rest (never auto-committed).
- **Budgets + an AI budget coach** — month-vs-budget, pace awareness, savings goals, a violet
  AI voice distinct from deterministic facts.
- **Insight detail, Trends, and a cash-flow Sankey** — the month's story, sparklines, and an
  income → categories → saved flow diagram.
- **Family mode (full-shared household ledger)** — two adults, one ledger: both see and act on the
  same accounts/transactions/budgets/review queue (Settings → Family, invite by email).
- **On-device polish** — biometric app lock (on by default, fails open), offline read cache with an
  "as of" indicator, a home-screen widget, launcher shortcuts, and an opt-in weekly-review nudge.
- **Suite integration** — provides `GET /cross-app/summary` (aggregates-only) consumed by
  Cookbook's grocery tile and the Dragonfly weekly digest; consumes Spotter for fitness
  cost-per-visit.

Start with [CLAUDE.md](CLAUDE.md) (build spec + locked decisions), then
[ARCHITECTURE.md](ARCHITECTURE.md) (as-built design) and [ROADMAP.md](ROADMAP.md) (road to 1.0 +
non-goals). Suite context lives in the Dragonfly repo and the host workspace docs.
