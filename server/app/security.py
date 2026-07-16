from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db

# Magpie is SSO-only (CLAUDE.md locked decision) — there is no /auth/login, so this only
# documents where a token comes from for the OpenAPI UI; the real path is POST /auth/suite.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/suite")


def create_access_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode(
        {"sub": subject, "exp": expire, "type": "access"},
        settings.secret_key,
        algorithm=settings.algorithm,
    )


def create_refresh_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    return jwt.encode(
        {"sub": subject, "exp": expire, "type": "refresh"},
        settings.secret_key,
        algorithm=settings.algorithm,
    )


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    from app.models.user import User

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        if payload.get("type") != "access":
            raise credentials_exception
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception
    return user


CurrentUser = Annotated[object, Depends(get_current_user)]


async def get_ledger_owner(
    current_user: Annotated[object, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """The user whose financial data the request operates on (family mode, CLAUDE.md household
    sharing): the household **owner** for a member, else the caller. Financial data endpoints depend
    on this instead of :func:`get_current_user`, so a household member reads and writes the one
    shared ledger. Identity/membership endpoints keep ``get_current_user`` (the real caller)."""
    from app.models.user import User
    from app.services.household_service import resolve_ledger_owner_id

    owner_id = await resolve_ledger_owner_id(db, current_user.id)
    if owner_id == current_user.id:
        return current_user
    owner = (await db.execute(select(User).where(User.id == owner_id))).scalar_one_or_none()
    return owner or current_user


# Financial data endpoints use this; it resolves a household member to the shared-ledger owner.
LedgerUser = Annotated[object, Depends(get_ledger_owner)]


async def get_cross_app_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Resolve the Magpie user from a sister-app cross-app token (federated awareness Link D —
    Cookbook reads grocery spend). RS256-only: Magpie post-dates the HS256 retirement plan, so
    there is no shared-secret fallback. The token must be a dragonfly-id service token with
    ``aud="cross-app"``; a Magpie session token or an SSO token (aud="suite") can never reach
    this surface."""
    from app.models.user import User
    from app.services.suite_auth import verify_cross_app_token

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    email = await verify_cross_app_token(token)
    if not email:
        raise credentials_exception
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception
    return user


CrossAppUser = Annotated[object, Depends(get_cross_app_user)]
