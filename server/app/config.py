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


settings = Settings()
