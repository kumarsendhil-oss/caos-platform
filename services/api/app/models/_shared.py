"""Shared column helpers used across every model."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column


def uuid_pk() -> Mapped[str]:
    return mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))


def created_at_col() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
