"""
app/security.py — password hashing, per Security Standard §1.

Covers the behaviour passlib used to hide: bcrypt's 72-byte limit, and
what happens when a stored hash is unusable. A login attempt must never be
able to turn a malformed input into a 500.
"""

from __future__ import annotations

import statistics
import time

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.security import (
    MAX_PASSWORD_BYTES,
    PasswordTooLongError,
    dummy_verify,
    hash_password,
    verify_password,
)

LOGIN = "/api/v1/auth/login"
PASSWORD = "correct-horse-battery-staple"


def test_hash_and_verify_roundtrip() -> None:
    hashed = hash_password(PASSWORD)
    assert verify_password(PASSWORD, hashed) is True
    assert verify_password("not-the-password", hashed) is False


def test_hashing_is_salted() -> None:
    """Two hashes of the same password must differ, or identical passwords are visible."""
    assert hash_password(PASSWORD) != hash_password(PASSWORD)


def test_hash_is_bcrypt_format() -> None:
    assert hash_password(PASSWORD).startswith("$2b$")


def test_password_at_the_byte_limit_is_accepted() -> None:
    at_limit = "a" * MAX_PASSWORD_BYTES
    assert verify_password(at_limit, hash_password(at_limit)) is True


def test_overlong_password_is_rejected_not_truncated() -> None:
    """
    bcrypt ignores anything past 72 bytes. Truncating silently would mean a
    user's password tail is not actually part of their password, so this
    refuses instead.
    """
    with pytest.raises(PasswordTooLongError):
        hash_password("a" * (MAX_PASSWORD_BYTES + 1))


def test_multibyte_password_is_measured_in_bytes_not_characters() -> None:
    """A 3-byte character means the limit bites well before 72 characters."""
    emoji = "🔒"  # 4 bytes in UTF-8
    assert len(emoji * 20) == 20  # 20 characters...
    with pytest.raises(PasswordTooLongError):
        hash_password(emoji * 20)  # ...but 80 bytes


def test_verify_returns_false_for_overlong_candidate() -> None:
    """Rather than raising — a long input at the login form must not 500."""
    assert verify_password("a" * 200, hash_password(PASSWORD)) is False


@pytest.mark.parametrize("bad_hash", ["", "not-a-hash", "$2b$12$truncated", "null"])
def test_verify_returns_false_for_an_unusable_stored_hash(bad_hash: str) -> None:
    assert verify_password(PASSWORD, bad_hash) is False


def test_dummy_verify_accepts_anything_without_raising() -> None:
    dummy_verify("")
    dummy_verify("a" * 500)
    dummy_verify("🔒" * 100)


async def test_unknown_email_takes_comparable_time_to_a_wrong_password(
    client: AsyncClient, session: AsyncSession
) -> None:
    """
    Security Standard §1 — an identical error message is only half of not
    revealing whether an account exists. Before the dummy-verify fix the
    unknown-email path skipped bcrypt entirely and returned in ~0ms against
    ~250ms for a real verification, leaking the same fact through timing.

    The threshold is deliberately loose: this is guarding against the
    hundred-fold gap that skipping bcrypt produces, not asserting constant
    time, which Python cannot promise anyway.
    """
    user = User(
        name="Senior Staff",
        email="senior@example.com",
        role="senior",
        hashed_password=hash_password(PASSWORD),
    )
    session.add(user)
    await session.flush()

    async def timed(email: str) -> float:
        samples = []
        for _ in range(3):
            start = time.perf_counter()
            response = await client.post(LOGIN, json={"email": email, "password": "wrong"})
            samples.append(time.perf_counter() - start)
            assert response.status_code == 401
        return statistics.median(samples)

    wrong_password = await timed(user.email)
    unknown_email = await timed("nobody@example.com")

    assert unknown_email > wrong_password * 0.25, (
        f"unknown-email login returned in {unknown_email * 1000:.1f}ms vs "
        f"{wrong_password * 1000:.1f}ms for a wrong password — the no-such-user "
        "path is skipping password verification and leaking account existence"
    )
