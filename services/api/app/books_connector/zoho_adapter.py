"""
ZohoAdapter — implements BooksConnector against the Zoho Books REST API v3,
using OAuth2 per client organization. Per ADR 0011.

STUB: the real OAuth2 flow and API calls are not wired yet — blocked on
Dev Readiness Checklist item P0-06 (Zoho Books sandbox spike) and ENV-07
(developer account + sandbox org). Structured to match TallyAdapter's
shape exactly so the Bookkeeping Agent's calling code never branches on
which adapter it's talking to.
"""

from __future__ import annotations

from app.books_connector.base import BooksConnector, DraftEntry, LedgerLine, PostedEntry
from app.config import settings


class ZohoNotConfiguredError(RuntimeError):
    """Raised when Zoho OAuth credentials aren't set — expected until Sprint 1-2 wiring lands."""


class ZohoAdapter(BooksConnector):
    def __init__(
        self,
        organization_id: str,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> None:
        self.organization_id = organization_id
        self.client_id = client_id or settings.zoho_oauth_client_id
        self.client_secret = client_secret or settings.zoho_oauth_client_secret

    def _require_configured(self) -> None:
        if not self.client_id or not self.client_secret:
            raise ZohoNotConfiguredError(
                "ZOHO_OAUTH_CLIENT_ID / ZOHO_OAUTH_CLIENT_SECRET are not set. "
                "Configure once P0-06 (Zoho sandbox spike) is complete — see "
                "Dev Readiness Checklist."
            )

    async def extract_purchase_register(self, client_id: str, period: str) -> list[LedgerLine]:
        self._require_configured()
        # STUB(#4): GET against Zoho Books REST API v3, normalized
        # to the same LedgerLine shape TallyAdapter produces (ZB-02). See
        # docs/STUB_ISSUES.md.
        raise NotImplementedError("STUB(#4) — ZohoAdapter.extract_purchase_register")

    async def extract_sales_register(self, client_id: str, period: str) -> list[LedgerLine]:
        self._require_configured()
        raise NotImplementedError("STUB(#4) — ZohoAdapter.extract_sales_register")

    async def extract_bank_book(self, client_id: str, period: str) -> list[LedgerLine]:
        self._require_configured()
        raise NotImplementedError("STUB(#4) — ZohoAdapter.extract_bank_book")

    async def post_entry(self, client_id: str, entry: DraftEntry) -> PostedEntry:
        self._require_configured()
        # STUB(#5): POST a Bill or Journal Entry via Zoho's API.
        # CG7's duplicate-check has already run by the time this is
        # called. Per ADR 0011 Amendment 1, resolve entry.tax_rate to this
        # organization's tax_id by direct rate match (cached per org), and
        # send entry.supplier_state / entry.place_of_supply as source and
        # destination of supply — Zoho computes the split server-side.
        # When the org has no tax rate matching entry.tax_rate, raise a
        # Task Engine exception rather than guessing, per BK-03's
        # missing-ledger pattern. See docs/STUB_ISSUES.md.
        raise NotImplementedError("STUB(#5) — ZohoAdapter.post_entry")

    async def connection_health(self, client_id: str) -> str:
        if not self.client_id:
            return "error"
        # STUB(#6): validate the stored refresh token is still
        # usable. See docs/STUB_ISSUES.md.
        return "unknown"
