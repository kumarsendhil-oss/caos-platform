"""CLIENT — master client record, anchor entity. Traces to ID, CB-01."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._shared import created_at_col, uuid_pk


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[str] = uuid_pk()
    legal_name: Mapped[str] = mapped_column(String(255))
    entity_type: Mapped[str] = mapped_column(String(50))
    gstin: Mapped[str | None] = mapped_column(String(15), nullable=True)
    primary_contact: Mapped[str | None] = mapped_column(String(255), nullable=True)
    billing_cycle: Mapped[str] = mapped_column(String(20), default="monthly")

    # Per ADR 0011 — drives which BooksConnector adapter this client's
    # downstream agents use. "tally" | "zoho_books".
    books_system: Mapped[str] = mapped_column(String(20), default="tally")

    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = created_at_col()
