"""VENDOR_MAPPING — learned vendor-name-to-ledger matches. Traces to BK-02."""

from __future__ import annotations

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._shared import uuid_pk


class VendorMapping(Base):
    __tablename__ = "vendor_mappings"

    id: Mapped[str] = uuid_pk()
    client_id: Mapped[str | None] = mapped_column(ForeignKey("clients.id"), nullable=True)
    vendor_name_raw: Mapped[str] = mapped_column(String(255))
    tally_ledger_name: Mapped[str] = mapped_column(String(255))
    match_confidence: Mapped[float | None] = mapped_column(nullable=True)
