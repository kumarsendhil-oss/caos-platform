"""Auth & Identity (ID) — POST /auth/login. Traces to ID-01."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from jose import jwt
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.errors import ApiError
from app.models.user import User
from app.security import dummy_verify, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: str
    name: str
    email: str
    role: str

    model_config = {"from_attributes": True}


class LoginResponse(BaseModel):
    access_token: str
    expires_at: datetime
    user: UserOut


def create_access_token(user: User) -> tuple[str, datetime]:
    expires_at = datetime.now(UTC) + timedelta(hours=settings.jwt_expiry_hours)
    payload = {"sub": user.id, "role": user.role, "exp": expires_at}
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)
    return token, expires_at


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, session: AsyncSession = Depends(get_session)) -> LoginResponse:
    result = await session.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    # Security Standard §1 — a failed login must not reveal whether the
    # account exists. The identical error message is only half of that: if
    # the no-such-user path skipped bcrypt, it would return measurably
    # faster and leak the same fact through timing. So verify either way.
    if user is None:
        dummy_verify(body.password)
        raise ApiError("invalid_credentials", "Email or password is incorrect.", status_code=401)

    if not verify_password(body.password, user.hashed_password):
        raise ApiError("invalid_credentials", "Email or password is incorrect.", status_code=401)

    token, expires_at = create_access_token(user)
    return LoginResponse(
        access_token=token, expires_at=expires_at, user=UserOut.model_validate(user)
    )
