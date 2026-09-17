"""
TallyAdapter — implements BooksConnector against TallyPrime's XML-over-HTTP
interface (default port 9000). Per ADR 0001.

STUB: the real HTTP/XML calls are not wired yet — that's Sprint 1-2 work,
blocked on Dev Readiness Checklist item P0-02 (confirming port 9000 is
externally reachable) and ENV-05 (TallyPrime API Explorer sandbox access).
This class exists so the interface boundary and duplicate-prevention call
site (CG7) are correct from day one, per Testing Strategy §2 — agents can
be written and unit-tested against this interface today, with the real
XML payload work slotting in without changing any calling code.
"""

from __future__ import annotations

from app.books_connector.base import BooksConnector, DraftEntry, LedgerLine, PostedEntry
from app.config import settings


class TallyNotConfiguredError(RuntimeError):
    """Raised when tally_connector_host isn't set — expected until Sprint 1-2 wiring lands."""


class TallyAdapter(BooksConnector):
    def __init__(self, host: str | None = None, port: int | None = None) -> None:
        self.host = host or settings.tally_connector_host
        self.port = port or settings.tally_connector_port

    def _require_configured(self) -> None:
        if not self.host:
            raise TallyNotConfiguredError(
                "TALLY_CONNECTOR_HOST is not set. Configure it once P0-02 "
                "(port 9000 reachability) is confirmed — see Dev Readiness Checklist."
            )

    async def extract_purchase_register(self, client_id: str, period: str) -> list[LedgerLine]:
        self._require_configured()
        # STUB(#1): XML-over-HTTP request against TallyPrime API
        # Explorer first (TC-01b), then the real Tally Cloud host. See
        # ADR 0001 and docs/STUB_ISSUES.md.
        raise NotImplementedError("STUB(#1) — TallyAdapter.extract_purchase_register")

    async def extract_sales_register(self, client_id: str, period: str) -> list[LedgerLine]:
        self._require_configured()
        raise NotImplementedError("STUB(#1) — TallyAdapter.extract_sales_register")

    async def extract_bank_book(self, client_id: str, period: str) -> list[LedgerLine]:
        self._require_configured()
        raise NotImplementedError("STUB(#1) — TallyAdapter.extract_bank_book")

    async def post_entry(self, client_id: str, entry: DraftEntry) -> PostedEntry:
        self._require_configured()
        # STUB(#2): XML voucher import. CG7's duplicate-check has
        # already run by the time this is called — do not re-check here.
        # Per ADR 0011 Amendment 1 this method owns the tax derivation:
        # compute the CGST/SGST/IGST amounts from entry.tax_rate against
        # entry.taxable_amount and select the matching tax ledger names.
        # Decimal throughout (CG5) — rounding on odd rates is the likely
        # bug site, so unit-test it directly.
        #
        # Per ADR 0011 Amendment 2, do NOT decide intra- vs inter-state
        # here by comparing entry.place_of_supply to entry.supplier_state.
        # That determination is made once above the BooksConnector
        # boundary and handed down; duplicating it here is exactly what
        # the amendment forbids, and Tally is the backend where getting it
        # wrong is silent (P0-02 finding #2). The state fields on
        # DraftEntry are two-digit numeric codes — translate to Tally's
        # full STATENAME at the edge, immediately before XML generation.
        # See docs/STUB_ISSUES.md.
        raise NotImplementedError("STUB(#2) — TallyAdapter.post_entry")

    async def connection_health(self, client_id: str) -> str:
        if not self.host:
            return "error"
        # STUB(#3): real ping against the Tally Cloud host. See docs/STUB_ISSUES.md.
        return "unknown"
