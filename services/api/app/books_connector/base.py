"""
BooksConnector — the interface both the Tally and Zoho adapters implement.

Per ADR 0011: every agent (Bookkeeping, Reconciliation, Working Paper) is
built against this interface's normalized schema, never against either
backend's native shape directly. No agent module should import
TallyAdapter or ZohoAdapter directly — resolve the correct adapter once,
via get_adapter_for_client(), and depend on BooksConnector from there on.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class LedgerLine:
    """Normalized purchase/sales register line — same shape regardless of adapter."""

    vendor_name: str
    vendor_gstin: str | None
    invoice_number: str
    invoice_date: str  # ISO 8601 date
    amount: Decimal
    hsn_code: str | None = None


@dataclass(frozen=True)
class DraftEntry:
    """
    A staged, approved entry ready to post — a Tally voucher or a Zoho Bill/Journal Entry.

    Per ADR 0011 Amendment 1, this carries tax *determinants* rather than
    computed tax amounts. Each adapter derives what its own backend needs:
    TallyAdapter computes the CGST/SGST/IGST split from tax_rate plus the
    two state codes and selects the tax ledger names; ZohoAdapter resolves
    tax_rate to a per-organization tax_id. Deriving at the edge keeps the
    shared shape backend-neutral and avoids the lossy amounts-to-rate
    round-trip (two rate configurations can yield the same rupee amount).

    LIMITATION — mixed-rate invoices. A single tax_rate assumes exactly one
    rate per entry. Real invoices can carry several rates across line items,
    and this shape does not represent that. It is explicitly deferred per
    the amendment's Open section, to be reconsidered when line-item-level
    extraction is built. Do not work around it by averaging rates or by
    silently splitting one invoice into multiple entries.
    """

    vendor_gstin: str | None
    invoice_number: str
    invoice_date: str  # ISO 8601 date
    taxable_amount: Decimal  # pre-tax line total
    tax_rate: Decimal  # percent, e.g. Decimal("18") for 18%
    place_of_supply: str  # state code, e.g. "TN"
    supplier_state: str  # state code, for intra- vs inter-state determination
    ledger_name: str


@dataclass(frozen=True)
class PostedEntry:
    """Result of a successful post, whichever adapter handled it."""

    external_id: str
    posting_system: str  # "tally_voucher" | "zoho_bill" | "zoho_journal"


class BooksConnector(ABC):
    """
    Every method here must be implemented by both TallyAdapter and
    ZohoAdapter. Downstream agents depend only on this interface.
    """

    @abstractmethod
    async def extract_purchase_register(self, client_id: str, period: str) -> list[LedgerLine]:
        """TC-02 / ZB-02 — read purchase register, normalized."""

    @abstractmethod
    async def extract_sales_register(self, client_id: str, period: str) -> list[LedgerLine]:
        """TC-02 / ZB-02 — read sales register, normalized."""

    @abstractmethod
    async def extract_bank_book(self, client_id: str, period: str) -> list[LedgerLine]:
        """TC-02 / ZB-02 — read bank book, normalized. Feeds Bank Reconciliation (BR)."""

    @abstractmethod
    async def post_entry(self, client_id: str, entry: DraftEntry) -> PostedEntry:
        """
        TC-04 / ZB-03 — post an approved draft entry.

        CG7's duplicate-prevention check runs BEFORE this is called, in
        the Bookkeeping Agent service layer — this method assumes the
        caller has already verified no matching entry exists.

        Per ADR 0011 Amendment 1, DraftEntry carries tax determinants, not
        computed amounts: deriving the backend's tax representation from
        tax_rate, place_of_supply and supplier_state is this method's
        responsibility, not the caller's.
        """

    @abstractmethod
    async def connection_health(self, client_id: str) -> str:
        """TC-05 / ZB-05 — 'healthy' | 'stale' | 'error', surfaced on Admin — Connections."""
