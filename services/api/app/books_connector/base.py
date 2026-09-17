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
    TallyAdapter computes the CGST/SGST/IGST amounts from tax_rate and
    selects the tax ledger names; ZohoAdapter resolves tax_rate to a
    per-organization tax_id.

    Per ADR 0011 Amendment 2, what neither adapter does is decide *which*
    jurisdiction applies. The intra- vs inter-state determination is made
    ONCE, above this interface, by a shared function — never per-adapter.
    P0-06 finding #9 is the reason: Zoho validates that choice and rejects
    a wrong one loudly (code 3032), while Tally does not validate at all
    and posts a wrong-but-plausible split silently. Two copies of one
    decision, where only one copy's mistakes are ever reported, drift in
    the direction of the silent backend. Deriving at the edge keeps the
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
    # Two-digit statutory GST state code, e.g. "33" (Tamil Nadu) — NOT the
    # two-letter alpha form and NOT the full state name. Per ADR 0011
    # Amendment 2 the numeric code is canonical throughout the platform,
    # because it is the only one of the three representations backed by a
    # fixed, government-assigned vocabulary. Each adapter translates to its
    # own backend's spelling at the edge: ZohoAdapter to alpha, TallyAdapter
    # to the full STATENAME.
    place_of_supply: str
    # Same encoding. Note this should agree with vendor_gstin[:2], which is
    # the same fact by another route — a mismatch is an extraction problem
    # worth a Task, not a field to silently prefer one way or the other.
    supplier_state: str
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
        computed amounts: deriving the backend's tax *representation* from
        tax_rate and the supplied jurisdiction is this method's
        responsibility, not the caller's.

        Per ADR 0011 Amendment 2, the intra- vs inter-state *determination*
        is NOT this method's responsibility. It is made once above this
        interface and handed down. Do not re-derive it here by comparing
        place_of_supply to supplier_state — that is the duplication the
        amendment exists to prevent.
        """

    @abstractmethod
    async def connection_health(self, client_id: str) -> str:
        """TC-05 / ZB-05 — 'healthy' | 'stale' | 'error', surfaced on Admin — Connections."""
