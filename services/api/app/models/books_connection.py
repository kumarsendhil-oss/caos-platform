"""
BOOKS_CONNECTION — a client's connection to their bookkeeping system,
either a Tally company or an OAuth-connected Zoho Books organization.

Generalized from the original TALLY_COMPANY entity per ADR 0011
(Multi-Backend Bookkeeping Connector). Traces to TC-01 to TC-08,
ZB-01 to ZB-05.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._shared import uuid_pk

BOOKS_SYSTEMS = ("tally", "zoho_books")


class BooksConnection(Base):
    __tablename__ = "books_connections"

    id: Mapped[str] = uuid_pk()
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), unique=True)
    books_system: Mapped[str] = mapped_column(String(20))  # tally | zoho_books

    # Tally-specific (set when books_system == "tally")
    tally_company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # primary_live | secondary_backup
    tally_connection_path: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Zoho-specific (set when books_system == "zoho_books")
    zoho_organization_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # connected | token_expired | revoked
    zoho_oauth_status: Mapped[str | None] = mapped_column(String(20), nullable=True)

    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # healthy | stale | error | unknown
    sync_health: Mapped[str] = mapped_column(String(20), default="unknown")
