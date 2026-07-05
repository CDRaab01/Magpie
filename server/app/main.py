import asyncio
import contextlib
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.config import settings
from app.ingest.poller import poll_loop
from app.limiter import limiter
from app.routers import accounts, auth, categories, imports, ingest, suite_auth, transactions

# Single source for the human-facing version, reused by GET /version below.
APP_VERSION = "0.1.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    poll_task = None
    if (
        settings.imap_host
        and settings.imap_user
        and settings.imap_password
        and settings.ingest_user_email
    ):
        poll_task = asyncio.create_task(poll_loop())
    yield
    if poll_task is not None:
        poll_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await poll_task


# Interactive docs are handy locally but an unnecessary surface once this is reachable
# over the tailnet.
app = FastAPI(
    title="Magpie API",
    version=APP_VERSION,
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
    openapi_url="/openapi.json" if settings.docs_enabled else None,
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# Safety net for database errors that slip past request validation. Without these, a
# constraint violation or an un-storable value surfaces as an opaque 500. Map them to clean
# 4xx so clients get a structured error and the logs stay quiet.
@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": "Request conflicts with an existing or missing related record."},
    )


@app.exception_handler(DBAPIError)
async def dbapi_error_handler(request: Request, exc: DBAPIError) -> Response:
    # SQLSTATE class "22" is a *data exception* — a value the client sent that Postgres
    # can't store. That's a 422. Anything else is a genuine server fault: re-raise so it
    # 500s and is logged.
    sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None)
    if sqlstate and str(sqlstate).startswith("22"):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": "Request contains a value that cannot be stored."},
        )
    raise exc


# CORS: credentials=True is incompatible with wildcard origins (browser spec) and
# unnecessary for the Android client, which uses Authorization Bearer headers.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next) -> Response:
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if settings.hsts_enabled:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


app.include_router(suite_auth.router)
app.include_router(auth.router)
app.include_router(accounts.router)
app.include_router(categories.router)
app.include_router(transactions.router)
app.include_router(imports.router)
app.include_router(ingest.router)


@app.get("/health", tags=["health"])
async def health() -> dict:
    return {"status": "ok"}


@app.get("/version", tags=["version"])
async def version() -> dict:
    # Unauthenticated (like /health) so the app can show what's running before/after login.
    return {
        "name": app.title,
        "version": APP_VERSION,
        "commit": settings.git_sha,
        "built_at": settings.built_at,
    }
