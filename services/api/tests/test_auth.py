"""
POST /auth/login and the token-rejection paths in app/routers/deps.py.

Traces to ID-01 (role-based login) and Security Standard §1-§2. The
rejection tests matter more than the happy path: Security Standard §1
requires that a failed login not reveal whether an account exists, and §2
requires the server to reject a bad token itself rather than relying on
the UI.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User
from app.routers.auth import pwd_context

# The login tests below cannot run in this environment: passlib 1.7.4 cannot
# drive bcrypt 5.0.0, so pwd_context.hash() AND .verify() both raise
# ValueError, which means POST /auth/login always 500s. pyproject pins
# passlib but not bcrypt, so a fresh `pip install -e ".[dev]"` reproduces it —
# including in CI. They are written and skip-marked rather than deleted so
# they run the moment the dependency is fixed. See the PR for detail.
_BCRYPT_BROKEN = True
try:
    pwd_context.hash("probe")
    _BCRYPT_BROKEN = False
except Exception:  # noqa: BLE001 — any failure here means hashing is unusable
    pass

requires_working_bcrypt = pytest.mark.skipif(
    _BCRYPT_BROKEN,
    reason="passlib 1.7.4 is incompatible with bcrypt 5.0.0 — login cannot run",
)

LOGIN = "/api/v1/auth/login"
# Any authenticated endpoint works for exercising deps.py's rejection paths.
PROTECTED = "/api/v1/tasks"

PASSWORD = "correct-horse-battery-staple"


@pytest.fixture
async def user(session: AsyncSession) -> User:
    """A real user with a usable password hash (login tests)."""
    u = User(
        name="Senior Staff",
        email="senior@example.com",
        role="senior",
        hashed_password=pwd_context.hash(PASSWORD),
    )
    session.add(u)
    await session.flush()
    return u


def _token(sub: str, *, expires_in_hours: float = 8) -> str:
    expiry = datetime.now(UTC) + timedelta(hours=expires_in_hours)
    return jwt.encode(
        {"sub": sub, "role": "senior", "exp": expiry},
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )


# --- login ---------------------------------------------------------------


@requires_working_bcrypt
async def test_login_returns_token_expiry_and_user(
    client: AsyncClient, user: User
) -> None:
    response = await client.post(LOGIN, json={"email": user.email, "password": PASSWORD})

    assert response.status_code == 200
    body = response.json()

    # The token is real and identifies this user.
    claims = jwt.decode(
        body["access_token"], settings.secret_key, algorithms=[settings.jwt_algorithm]
    )
    assert claims["sub"] == user.id
    assert claims["role"] == "senior"

    # Expiry matches the configured session length (Security Standard §1 —
    # no indefinitely-lived sessions on shared office devices).
    expires_at = datetime.fromisoformat(body["expires_at"])
    expected = datetime.now(UTC) + timedelta(hours=settings.jwt_expiry_hours)
    assert abs((expires_at - expected).total_seconds()) < 60
    assert claims["exp"] == int(expires_at.timestamp())

    # The right user comes back, and no secret material rides along.
    assert body["user"] == {
        "id": user.id,
        "name": "Senior Staff",
        "email": "senior@example.com",
        "role": "senior",
    }
    assert "hashed_password" not in body["user"]


@requires_working_bcrypt
async def test_login_issues_a_token_that_actually_works(
    client: AsyncClient, user: User
) -> None:
    """End-to-end: the token login hands out is accepted by a protected route."""
    login = await client.post(LOGIN, json={"email": user.email, "password": PASSWORD})
    token = login.json()["access_token"]

    response = await client.get(PROTECTED, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200


@requires_working_bcrypt
async def test_wrong_password_is_rejected(client: AsyncClient, user: User) -> None:
    response = await client.post(LOGIN, json={"email": user.email, "password": "wrong"})
    assert response.status_code == 401


@requires_working_bcrypt
async def test_unknown_email_is_rejected(client: AsyncClient, user: User) -> None:
    response = await client.post(
        LOGIN, json={"email": "nobody@example.com", "password": PASSWORD}
    )
    assert response.status_code == 401


@requires_working_bcrypt
async def test_failed_login_does_not_reveal_whether_the_account_exists(
    client: AsyncClient, user: User
) -> None:
    """
    Security Standard §1 — a failed login must not tell an attacker whether
    they guessed a real email. Both failures must be indistinguishable.
    """
    wrong_password = await client.post(
        LOGIN, json={"email": user.email, "password": "wrong"}
    )
    unknown_email = await client.post(
        LOGIN, json={"email": "nobody@example.com", "password": PASSWORD}
    )

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()
    # And the message itself must not name which half was wrong.
    message = wrong_password.json()["message"].lower()
    assert "email or password" in message
    assert "no such user" not in message
    assert "not found" not in message


@pytest.fixture
async def token_user(session: AsyncSession) -> User:
    """A user for token tests — no password hashing, so bcrypt is not involved."""
    u = User(
        name="Token User",
        email="token@example.com",
        role="senior",
        hashed_password="not-used-by-these-tests",
    )
    session.add(u)
    await session.flush()
    return u


# --- deps.py token rejection ---------------------------------------------


async def test_malformed_token_is_rejected(client: AsyncClient) -> None:
    response = await client.get(
        PROTECTED, headers={"Authorization": "Bearer not-a-jwt-at-all"}
    )
    assert response.status_code == 401
    assert response.json()["error_code"] == "invalid_token"


async def test_token_signed_with_the_wrong_key_is_rejected(client: AsyncClient) -> None:
    """A structurally valid JWT is not enough — the signature must verify."""
    forged = jwt.encode(
        {"sub": "whoever", "exp": datetime.now(UTC) + timedelta(hours=1)},
        "not-the-real-secret",
        algorithm=settings.jwt_algorithm,
    )
    response = await client.get(PROTECTED, headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401


async def test_expired_token_is_rejected(client: AsyncClient, token_user: User) -> None:
    """Security Standard §1 — sessions expire; an expired one must not work."""
    expired = _token(token_user.id, expires_in_hours=-1)
    response = await client.get(PROTECTED, headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 401
    assert response.json()["error_code"] == "invalid_token"


async def test_valid_token_for_a_deleted_user_is_rejected(
    client: AsyncClient, session: AsyncSession, token_user: User
) -> None:
    """
    A correctly-signed, unexpired token whose subject no longer exists must
    be rejected — otherwise a removed staff member keeps access until their
    token expires.
    """
    token = _token(token_user.id)
    await session.delete(token_user)
    await session.flush()

    response = await client.get(PROTECTED, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert response.json()["error_code"] == "invalid_token"


async def test_missing_authorization_header_is_rejected(client: AsyncClient) -> None:
    response = await client.get(PROTECTED)
    assert response.status_code == 403
