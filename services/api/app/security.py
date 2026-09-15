"""
Password hashing, per Security Standard §1.

Uses the `bcrypt` library directly rather than passlib. passlib 1.7.4 (the
latest release, from 2020) reads `bcrypt.__about__.__version__`, which
bcrypt removed in 4.1 — so passlib cannot drive any current bcrypt, and
both hashing and verification raise. Pinning bcrypt below 4.1 would have
frozen a security-critical native dependency on an old build to satisfy an
unmaintained wrapper; using bcrypt directly removes the wrapper instead.

Everything algorithm-specific lives in this module, so moving to argon2id
later (the stronger choice if this ever becomes internet-facing) is a
one-file change rather than a search across the codebase.
"""

from __future__ import annotations

import contextlib

import bcrypt

# bcrypt operates on at most 72 bytes and, since 5.0, raises rather than
# silently truncating. Passwords are rejected above this rather than cut
# down, so nobody ends up with a password whose tail is ignored. If
# arbitrary-length passwords are ever needed, pre-hash with SHA-256 and
# base64 before bcrypt — but that is a hash-format decision, so make it
# deliberately rather than as a quiet workaround here.
MAX_PASSWORD_BYTES = 72

# Used to keep verification time comparable when no user matches, so a
# failed login does not reveal whether the account exists (Security
# Standard §1). Generated once at import; the value is never a real
# password's hash, so it can never verify against anything.
_DUMMY_HASH = bcrypt.hashpw(b"not-a-real-password", bcrypt.gensalt())


class PasswordTooLongError(ValueError):
    """Raised when a password exceeds what bcrypt can hash."""


def hash_password(password: str) -> str:
    """Hash a new password for storage."""
    raw = password.encode("utf-8")
    if len(raw) > MAX_PASSWORD_BYTES:
        raise PasswordTooLongError(
            f"Password must be at most {MAX_PASSWORD_BYTES} bytes when UTF-8 encoded."
        )
    return bcrypt.hashpw(raw, bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, hashed: str) -> bool:
    """
    Check a password against a stored hash.

    Returns False rather than raising for anything unusable — an
    over-length candidate, a malformed or non-bcrypt stored hash. A login
    attempt must not be able to turn a bad input into a 500.
    """
    raw = password.encode("utf-8")
    if len(raw) > MAX_PASSWORD_BYTES:
        return False
    try:
        return bcrypt.checkpw(raw, hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def dummy_verify(password: str) -> None:
    """
    Burn roughly one verification's worth of time against a throwaway hash.

    Called on the no-such-user path so that an unknown email and a wrong
    password take comparable time. Without it, the unknown-email branch
    skips bcrypt entirely and returns measurably faster, which leaks
    whether an account exists — the thing Security Standard §1's identical
    error message exists to prevent.
    """
    raw = password.encode("utf-8")[:MAX_PASSWORD_BYTES]
    with contextlib.suppress(ValueError, TypeError):
        bcrypt.checkpw(raw, _DUMMY_HASH)
