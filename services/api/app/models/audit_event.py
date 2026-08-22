"""
AUDIT_EVENT — immutable, append-only record of approvals, overrides, and
reassignments, written by AuditTrailService (never the application logger).
Traces to ID-05, Security Standard §5, Logging Standard §5.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._shared import created_at_col, uuid_pk


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = uuid_pk()
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(50))
    subject_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    practice_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    occurred_at: Mapped[datetime] = created_at_col()

    # No update/delete path is exposed anywhere in the application layer —
    # this table is treated as insert-only by convention (Security Standard §5).
