"""Auth & Identity (ID) — POST /auth/login. Traces to ID-01."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from jose import jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.errors import ApiError
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


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
    if user is None or not pwd_context.verify(body.password, user.hashed_password):
        raise ApiError("invalid_credentials", "Email or password is incorrect.", status_code=401)

    token, expires_at = create_access_token(user)
    return LoginResponse(
        access_token=token, expires_at=expires_at, user=UserOut.model_validate(user)
    )
