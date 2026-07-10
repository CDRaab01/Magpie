from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str

    # Test-suite escape hatch: SQLAlchemy's default pool binds pooled asyncpg connections to
    # the event loop that created them, which fights pytest-asyncio's per-test loops. NullPool
    # opens a fresh connection per session — slower, loop-safe. The conftest enables it;
    # deployments leave it off.
    db_nullpool: bool = False

    # Magpie is tailnet-only by design (Tailscale Serve, no Cloudflare tunnel) — trust_proxy
    # and hsts_enabled exist for parity with the suite's other apps' security-header middleware,
    # but there is no public-hostname deployment shape here to enable them for.
    trust_proxy: bool = False
    hsts_enabled: bool = False
    # Expose the interactive API docs (/docs, /redoc, /openapi.json).
    docs_enabled: bool = True

    # Build/deploy stamp surfaced by GET /version so the app can show what's running
    # (and confirm a redeploy landed). Injected at deploy time; "unknown" for a manual/dev run.
    git_sha: str = "unknown"
    built_at: str = "unknown"

    # Local session tokens minted after a successful suite login (Phase 1). Magpie has no
    # password auth of its own — this key only ever signs/verifies Magpie's own short-lived
    # access/refresh tokens, never a suite token (those are RS256, verified via JWKS below).
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Suite SSO (CLAUDE.md locked decision: SSO-only, no password auth ever). When
    # suite_jwks_url + suite_issuer are set, POST /auth/suite accepts a suite access token
    # (RS256, from the Dragonfly identity server), validates it against the published JWKS,
    # and trades it for a Magpie session — linking by email. Unset ⇒ the endpoint 404s.
    suite_jwks_url: str | None = None
    suite_issuer: str | None = None
    suite_audience: str = "suite"
    # Timeout (seconds) for the outbound JWKS fetch.
    external_timeout_seconds: float = 8.0

    # Email ingestion (CLAUDE.md Phase 4). Unset imap_host ⇒ the lifespan poller never starts
    # — same "absence disables the feature" pattern as suite_jwks_url above. Read-only by
    # design (CLAUDE.md §8): the ingest module only ever fetches, never deletes/moves mail.
    imap_host: str | None = None
    imap_port: int = 993
    imap_user: str | None = None
    imap_password: str | None = None
    imap_label: str = "magpie-ingest"
    imap_poll_interval_minutes: int = 15
    # Whose accounts a parsed event's last4 should be matched against — this Magpie instance
    # is single-household, but every table is still user-scoped per suite convention, so the
    # poller needs to know which user's accounts to match against without an HTTP request
    # driving it.
    ingest_user_email: str | None = None

    # F18: Magpie's "months" are the OWNER's local months, not UTC. A transaction date derived
    # from a timestamp (an email whose body has no date line) is converted to this zone before
    # the calendar date is taken, so an 11pm-local swipe on the last of the month doesn't roll
    # into the next month because the server clock is UTC. IANA name; single-household.
    owner_timezone: str = "America/Chicago"

    # Deviation alerts (CLAUDE.md Phase 6). Unset ntfy_base_url ⇒ the sweep never publishes —
    # same "absence disables the feature" pattern as imap_host above.
    ntfy_base_url: str | None = None
    ntfy_topic: str = "magpie-alerts"
    sweep_interval_minutes: int = 15
    # Per-account freshness sweep (CLAUDE.md §5): an account that *was* receiving email alerts but
    # hasn't in this many days may have had its alerts silently turned off — page once (F: silent
    # alert-decay is the failure mode this catches). Generous, since a rarely-used card is normal.
    account_freshness_days: int = 14
    # CLAUDE.md §2: a pending auth hold with no posted match after this many days auto-drops with
    # an audit note. The gas-station $1 pre-auth is the canonical case.
    auth_hold_days: int = 7

    # Spending-anomaly sweeps (ROADMAP #19a — the proactive half of "watch my spending").
    # Deterministic thresholds; an LLM narration line is optional (#19) and never the trigger.
    # (1) A large charge at a merchant never seen before, within the recency window (older
    #     first-appearances are just the backfill, not news).
    anomaly_large_charge_cents: int = 20000  # $200
    anomaly_new_merchant_days: int = 7
    # (2) A category whose month-to-date spend runs well over its trailing full-month median.
    #     `factor` is the "well over" multiplier; `floor` suppresses noise on tiny categories;
    #     a median needs `min_months` of trailing history over a `trailing_months` window.
    anomaly_category_factor: float = 1.5
    anomaly_category_floor_cents: int = 15000  # $150
    anomaly_category_trailing_months: int = 6
    anomaly_category_min_months: int = 3

    # AI category drafts (CLAUDE.md §6/Phase 7). Local LM Studio only — never a hosted model,
    # this data never leaves the host. Unset ⇒ the AI stage never runs (rule evaluation just
    # falls through to needs_review with no draft, same as before Phase 7).
    llm_base_url: str | None = None
    llm_model: str = "local-model"


settings = Settings()
