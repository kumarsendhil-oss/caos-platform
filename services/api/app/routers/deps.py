"""
Server-side role enforcement, per Security Standard §2: "a UI-only
restriction would silently violate this the moment anyone calls the API
directly" — so every protected route depends on get_current_user (or
require_role) rather than trusting the frontend to hide a button.
"""

from __future__ import annotations

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.errors import ApiError
from app.models.user import User

bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    try:
        payload = jwt.decode(
            credentials.credentials, settings.secret_key, algorithms=[settings.jwt_algorithm]
        )
    except JWTError as exc:
        raise ApiError("invalid_token", "Session is invalid or expired.", status_code=401) from exc

    user = await session.get(User, payload.get("sub"))
    if user is None:
        raise ApiError("invalid_token", "Session is invalid or expired.", status_code=401)
    return user


def require_role(*allowed_roles: str):
    async def _check(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_roles:
            raise ApiError(
                "forbidden",
                f"This action requires one of: {', '.join(allowed_roles)}.",
                status_code=403,
            )
        return user

    return _check
