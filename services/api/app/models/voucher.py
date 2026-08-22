"""
VOUCHER — a draft or posted books-system entry, with confidence score.
Traces to BK-01 to BK-08.

books_connection_id (renamed from tally_company_id per ADR 0011) and
posting_system let this same table represent either a Tally voucher or
a Zoho Bill/Journal Entry — the Bookkeeping Agent and CG7's
duplicate-prevention check both operate on this table regardless of
which adapter eventually receives the post.
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._shared import uuid_pk


class Voucher(Base):
    __tablename__ = "vouchers"

    id: Mapped[str] = uuid_pk()
    extracted_data_id: Mapped[str | None] = mapped_column(
        ForeignKey("extracted_data.id"), nullable=True
    )
    books_connection_id: Mapped[str | None] = mapped_column(
        ForeignKey("books_connections.id"), nullable=True
    )

    # tally_voucher | zoho_bill | zoho_journal
    posting_system: Mapped[str | None] = mapped_column(String(20), nullable=True)
    voucher_type: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # CG5 — Decimal, never float
    amount: Mapped[str | None] = mapped_column(Numeric(14, 2), nullable=True)
    cgst: Mapped[str | None] = mapped_column(Numeric(14, 2), nullable=True)
    sgst: Mapped[str | None] = mapped_column(Numeric(14, 2), nullable=True)
    igst: Mapped[str | None] = mapped_column(Numeric(14, 2), nullable=True)

    confidence: Mapped[float | None] = mapped_column(nullable=True)
    # staged | approved | rejected | posted
    status: Mapped[str] = mapped_column(String(20), default="staged")

    # CG7 duplicate-prevention check fields
    vendor_gstin: Mapped[str | None] = mapped_column(String(15), nullable=True)
    invoice_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
