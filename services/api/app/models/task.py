"""
TASK — every human-touch item any agent raises, per ADR 0005 (Task Engine
as the shared backbone). Traces to TE-01 to TE-09.

linked_record_type / linked_record_id are a deliberate polymorphic
reference (per the ER diagram's note) — a Task can be raised by any
module (a voucher, a reconciliation mismatch, a document, ...), and
forcing a rigid FK per source-entity type would misrepresent the Task
Engine's actual flexibility.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._shared import created_at_col, uuid_pk

STATUSES = ("open", "in_progress", "completed", "escalated")
OUTCOMES = ("approved", "rejected", "edited")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = uuid_pk()
    task_type: Mapped[str] = mapped_column(String(100), index=True)
    client_id: Mapped[str | None] = mapped_column(ForeignKey("clients.id"), nullable=True)
    assignee_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    # TE-02 routing target. A RoutingRule names a *role*, not a person, and
    # nothing in the PRD or ADR 0005 specifies how to pick one user among
    # several holding that role — so routing sets the role here and leaves
    # assignee_id open for a human to claim or for TE-03 reassignment.
    # Escalation (TE-04) overwrites this with the next role up the ladder.
    assigned_role: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)

    linked_record_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    linked_record_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    outcome: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_by_agent: Mapped[str | None] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = created_at_col()
