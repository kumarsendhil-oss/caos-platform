"""USER — staff member (Proprietor / Senior / Junior). Traces to ID-01."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._shared import created_at_col, uuid_pk

ROLES = ("proprietor", "senior", "junior")


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = uuid_pk()
    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))  # proprietor | senior | junior
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = created_at_col()
