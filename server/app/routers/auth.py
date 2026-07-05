from fastapi import APIRouter, HTTPException, Request, status
from jose import JWTError, jwt

from app.config import settings
from app.limiter import limiter
from app.schemas.auth import RefreshRequest, TokenResponse
from app.security import create_access_token, create_refresh_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("10/minute")
async def refresh(request: Request, req: RefreshRequest):
    """Redeem a refresh token minted by /auth/suite for a new access/refresh pair.

    Magpie is SSO-only, but re-running the browser sign-in flow every 30 minutes (the access
    token TTL) would be unusable — this is that gap closed. No DB lookup needed: the token's
    own signature + "type": "refresh" claim is sufficient (mirrors Cookbook's /auth/refresh).
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
    )
    try:
        payload = jwt.decode(
            req.refresh_token, settings.secret_key, algorithms=[settings.algorithm]
        )
        if payload.get("type") != "refresh":
            raise credentials_exception
        user_id: str | None = payload.get("sub")
        if not user_id:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    return TokenResponse(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
    )
