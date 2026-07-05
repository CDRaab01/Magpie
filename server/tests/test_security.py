import uuid

import pytest
from fastapi import HTTPException
from jose import jwt

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.user import User
from app.security import create_access_token, create_refresh_token, get_current_user


def _unique_email() -> str:
    return f"direct-test-{uuid.uuid4().hex[:8]}@magpie.test"


def test_access_token_roundtrip():
    token = create_access_token("user-123")
    payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    assert payload["sub"] == "user-123"
    assert payload["type"] == "access"


def test_refresh_token_roundtrip():
    token = create_refresh_token("user-123")
    payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    assert payload["sub"] == "user-123"
    assert payload["type"] == "refresh"


async def test_get_current_user_resolves_real_user():
    async with AsyncSessionLocal() as session:
        user = User(name="Direct Test", email=_unique_email())
        session.add(user)
        await session.commit()
        await session.refresh(user)

        resolved = await get_current_user(token=create_access_token(str(user.id)), db=session)
        assert resolved.id == user.id


async def test_get_current_user_rejects_a_refresh_token():
    # A refresh token must never authorize a request — only "type": "access" is accepted.
    async with AsyncSessionLocal() as session:
        user = User(name="Direct Test 2", email=_unique_email())
        session.add(user)
        await session.commit()
        await session.refresh(user)

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token=create_refresh_token(str(user.id)), db=session)
        assert exc_info.value.status_code == 401


async def test_get_current_user_rejects_unknown_subject():
    async with AsyncSessionLocal() as session:
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(
                token=create_access_token("00000000-0000-0000-0000-000000000000"), db=session
            )
        assert exc_info.value.status_code == 401
