from __future__ import annotations

import pytest

from app.books_connector import TallyAdapter, ZohoAdapter, get_adapter_for_connection
from app.books_connector.tally_adapter import TallyNotConfiguredError
from app.books_connector.zoho_adapter import ZohoNotConfiguredError
from app.models.books_connection import BooksConnection


def test_resolver_returns_tally_adapter_for_tally_client() -> None:
    """Per ADR 0011: books_system on the connection drives adapter dispatch."""
    connection = BooksConnection(
        client_id="c1", books_system="tally", tally_company_name="Coastal Components"
    )
    adapter = get_adapter_for_connection(connection)
    assert isinstance(adapter, TallyAdapter)


def test_resolver_returns_zoho_adapter_for_zoho_client() -> None:
    connection = BooksConnection(
        client_id="c2", books_system="zoho_books", zoho_organization_id="sr-enterprises-org"
    )
    adapter = get_adapter_for_connection(connection)
    assert isinstance(adapter, ZohoAdapter)
    assert adapter.organization_id == "sr-enterprises-org"


def test_resolver_rejects_zoho_without_organization_id() -> None:
    connection = BooksConnection(
        client_id="c3", books_system="zoho_books", zoho_organization_id=None
    )
    with pytest.raises(ValueError, match="no organization_id"):
        get_adapter_for_connection(connection)


def test_resolver_rejects_unknown_books_system() -> None:
    connection = BooksConnection(client_id="c4", books_system="quickbooks")
    with pytest.raises(ValueError, match="Unknown books_system"):
        get_adapter_for_connection(connection)


async def test_tally_adapter_raises_when_not_configured() -> None:
    """Expected until Sprint 1-2 wires the real XML-over-HTTP calls (P0-02)."""
    adapter = TallyAdapter(host="")
    with pytest.raises(TallyNotConfiguredError):
        await adapter.extract_purchase_register(client_id="c1", period="2026-08")


async def test_zoho_adapter_raises_when_not_configured() -> None:
    """Expected until Sprint 1-2 wires the real OAuth2/API calls (P0-06)."""
    adapter = ZohoAdapter(organization_id="org1", client_id="", client_secret="")
    with pytest.raises(ZohoNotConfiguredError):
        await adapter.extract_purchase_register(client_id="c1", period="2026-08")
