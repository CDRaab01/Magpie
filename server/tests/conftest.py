import asyncio
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

# Must be set before any `app.*` import: the engine is built at app.database import time.
os.environ.setdefault("DB_NULLPOOL", "true")
os.environ.setdefault("SECRET_KEY", "ci-test-secret-key-not-for-production")


# --- The test suite must never touch the production database -------------------------------
#
# `app/config.py` falls back to `server/.env` when DATABASE_URL is unset — and on the deploy
# host that file points at the LIVE financial database (`magpie` on :5436). CI was only ever
# safe by accident: its workflow exports `DATABASE_URL=.../magpie_test`. A bare `pytest` on the
# host resolved to prod and wrote test users, accounts and transactions straight into real
# money (found 2026-07-09: ~456 test users and ~400 test accounts had accumulated there).
#
# So the database *name* is pinned here rather than inherited: same server, same credentials,
# a throwaway `*_test` database. CLAUDE.md §9 calls for a throwaway DB — this is what makes
# that true instead of aspirational.


_db_url = os.environ.get("DATABASE_URL", "")
if not _db_url:
    _env_file = Path(__file__).resolve().parent.parent / ".env"
    _lines = _env_file.read_text().splitlines() if _env_file.exists() else []
    _db_url = next(
        (ln.split("=", 1)[1].strip() for ln in _lines if ln.strip().startswith("DATABASE_URL=")),
        "",
    )
if not _db_url:
    raise RuntimeError("No DATABASE_URL in the environment or server/.env — cannot run tests.")

_base, _, _name = _db_url.rpartition("/")
if not _name.endswith("_test"):
    _db_url = f"{_base}/{_name}_test"
os.environ["DATABASE_URL"] = _db_url

# Tripwire: if the redirect above ever fails to hold (a URL with a query string, a future
# refactor), stop the run rather than let create_all/commits reach real financial data.
if not os.environ["DATABASE_URL"].rpartition("/")[2].endswith("_test"):
    raise RuntimeError(f"Refusing to run tests against a non-test database: {_db_url!r}")

# Migrate the way CI does (`alembic upgrade head`, then pytest). `setup_tables`' create_all
# builds tables but never runs *data* migrations, so a genuinely fresh database would have no
# seeded shared categories and a dozen tests would fail on `KeyError: 'Groceries'`. That went
# unnoticed while the suite was quietly running against the already-migrated prod database.
# A subprocess, because alembic's async env.py wants an event loop of its own.
subprocess.run(
    [sys.executable, "-m", "alembic", "upgrade", "head"],
    cwd=Path(__file__).resolve().parent.parent,
    check=True,
    capture_output=True,
)

import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient
from jose import jwk
from jose import jwt as jose_jwt

from app.config import settings
from app.database import Base, engine
from app.limiter import limiter
from app.main import app

limiter.enabled = False

# --- The suite-token test helper (Phase 1 exit criteria) ---------------------------------
#
# Magpie is SSO-only (CLAUDE.md locked decision): there is no /auth/register or /auth/login,
# so every test that needs an authenticated user goes through the suite-token flow. This
# generates one local RSA keypair for the whole test session and stubs the JWKS fetch to
# serve its public half — letting tests mint valid RS256 "suite" tokens without touching the
# real dragonfly-id server (mirrors Cookbook's tests/test_suite_auth.py pattern; centralized
# here rather than per-test-file, since Magpie has no other way to authenticate at all).

TEST_ISSUER = "http://id.test"
_KID = "test-kid"
_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PRIVATE_PEM = _key.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
).decode()
_PUBLIC_PEM = (
    _key.public_key()
    .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    .decode()
)


def _jwks() -> dict:
    d = jwk.construct(_PUBLIC_PEM, "RS256").to_dict()
    d.update({"kid": _KID, "use": "sig", "alg": "RS256"})
    return {"keys": [d]}


def suite_token(
    email: str, *, iss: str = TEST_ISSUER, aud: str = "suite", name: str = "SSO User"
) -> str:
    """Mint a locally-signed RS256 suite token — the shape dragonfly-id issues — for tests.
    Exported for use by any test file that needs an authenticated request."""
    now = int(time.time())
    claims = {
        "iss": iss,
        "sub": "suite-user-1",
        "aud": aud,
        "email": email,
        "name": name,
        "iat": now,
        "exp": now + 300,
    }
    return jose_jwt.encode(claims, _PRIVATE_PEM, algorithm="RS256", headers={"kid": _KID})


@pytest.fixture
def make_suite_token():
    """Fixture-injected access to `suite_token`, instead of a cross-file import.

    Without an `__init__.py` in tests/, pytest auto-loads this file as top-level `conftest`
    while `from tests.conftest import suite_token` elsewhere resolves via the dotted package
    path — two distinct module objects, each running the module-level RSA keygen once, so a
    token minted through one and verified through the other's JWKS fails signature checks.
    Fixture injection always resolves through pytest's single cached conftest instance, so it
    sidesteps the issue entirely. Discovered the hard way: see the Phase 1 build notes.
    """
    return suite_token


@pytest.fixture
def suite_enabled(monkeypatch):
    """Point the app at the local test JWKS instead of a real identity server."""
    monkeypatch.setattr(settings, "suite_jwks_url", "http://id.test/jwks")
    monkeypatch.setattr(settings, "suite_issuer", TEST_ISSUER)
    monkeypatch.setattr(settings, "suite_audience", "suite")

    async def _fake_fetch(*, force: bool = False):
        return _jwks()

    monkeypatch.setattr("app.services.suite_auth._fetch_jwks", _fake_fetch)


# --- Standard suite fixtures --------------------------------------------------------------


@pytest.fixture(scope="session")
def event_loop():
    """Share a single event loop across the whole test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_tables():
    """Ensure all tables exist before any test runs (safe to call after alembic)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    yield


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def auth_client(client, suite_enabled):
    """HTTP client pre-authenticated as a fresh unique test user, via the suite-token flow —
    Magpie has no password login to authenticate through."""
    uid = uuid.uuid4().hex[:8]
    email = f"test_{uid}@magpie.test"
    resp = await client.post("/auth/suite", json={"suite_token": suite_token(email)})
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client
