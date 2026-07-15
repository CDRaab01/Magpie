from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.limiter import limiter
from app.schemas.auth import SuiteLoginRequest, TokenResponse, UserOut
from app.security import CurrentUser
from app.services.suite_auth import suite_login

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser):
    """The signed-in account (name + email), for the Settings header. Identity is the SSO user
    linked at /auth/suite — Magpie stores no password of its own."""
    return UserOut(name=user.name, email=user.email)


@router.post("/suite", response_model=TokenResponse)
@limiter.limit("10/minute")
async def suite(
    request: Request,
    req: SuiteLoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Trade a Dragonfly suite token for a Magpie session.

    This is Magpie's ONLY auth endpoint — there is no /auth/register or /auth/login
    (CLAUDE.md locked decision: SSO-only). Disabled (404) unless suite_jwks_url +
    suite_issuer are configured.
    """
    return await suite_login(db, req.suite_token)
