"""EMAIL_SENDER_MAP — learned sender-address-to-client mapping. Traces to EI-02, EI-06."""

from __future__ import annotations

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._shared import uuid_pk


class EmailSenderMap(Base):
    __tablename__ = "email_sender_maps"

    id: Mapped[str] = uuid_pk()
    client_id: Mapped[str | None] = mapped_column(ForeignKey("clients.id"), nullable=True)
    sender_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sender_address: Mapped[str | None] = mapped_column(String(255), nullable=True)
