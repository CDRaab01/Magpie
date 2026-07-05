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


settings = Settings()
