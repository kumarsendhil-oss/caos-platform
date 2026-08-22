"""DOCUMENT and EXTRACTED_DATA — Document Intake. Traces to DI-01 to DI-04."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._shared import created_at_col, uuid_pk


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = uuid_pk()
    client_id: Mapped[str | None] = mapped_column(ForeignKey("clients.id"), nullable=True)
    source: Mapped[str] = mapped_column(String(20))  # email | dropbox
    dropbox_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    doc_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    received_at: Mapped[datetime] = created_at_col()


class ExtractedData(Base):
    __tablename__ = "extracted_data"

    id: Mapped[str] = uuid_pk()
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), unique=True)
    vendor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gstin: Mapped[str | None] = mapped_column(String(15), nullable=True)
    # CG5 — Decimal, never float
    amount: Mapped[str | None] = mapped_column(Numeric(14, 2), nullable=True)
    hsn_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    confidence: Mapped[float | None] = mapped_column(nullable=True)
