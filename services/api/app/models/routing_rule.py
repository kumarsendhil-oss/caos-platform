"""
ROUTING_RULE — the task-type → default-role assignment table, per TE-02
and ADR 0005.

ADR 0005 is explicit that this is "a real design artifact that needs to
be built deliberately, ideally in collaboration with the proprietor" —
so it is configuration the proprietor edits through
GET/PUT /admin/routing-rules, never hardcoded branching in agent code.
The same ADR gives the reason: routine tasks must "land on junior/senior
staff rather than defaulting to the proprietor and defeating the
purpose."

Not present in audit-platform-ER-core.mermaid (v0.2) — this is a
genuinely new entity introduced by TE-02, not a rename of an existing
one. The ER diagram should gain it when next revised.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._shared import created_at_col, uuid_pk


class RoutingRule(Base):
    __tablename__ = "routing_rules"

    id: Mapped[str] = uuid_pk()

    # One rule per task type — the lookup key used by TaskEngine.create_task
    # and escalate_overdue, hence unique + indexed.
    task_type: Mapped[str] = mapped_column(String(100), unique=True, index=True)

    # proprietor | senior | junior — see app/models/user.py ROLES.
    default_role: Mapped[str] = mapped_column(String(20))

    # Hours from creation before the task is considered overdue (TE-04).
    escalate_after_hours: Mapped[int] = mapped_column(Integer, default=24)

    created_at: Mapped[datetime] = created_at_col()
