"""
Resolves the correct BooksConnector adapter for a client, based on their
configured books_system (CB-01). This is the ONE place in the codebase
that knows both adapter classes exist — every agent above this layer only
ever sees a BooksConnector.
"""

from __future__ import annotations

from app.books_connector.base import BooksConnector
from app.books_connector.tally_adapter import TallyAdapter
from app.books_connector.zoho_adapter import ZohoAdapter
from app.models.books_connection import BooksConnection


def get_adapter_for_connection(connection: BooksConnection) -> BooksConnector:
    """
    Per ADR 0011 / CG11: this dispatch is configuration-driven, not a
    practice-specific customization — it belongs in core.
    """
    if connection.books_system == "tally":
        return TallyAdapter()
    if connection.books_system == "zoho_books":
        if not connection.zoho_organization_id:
            raise ValueError(
                f"BooksConnection {connection.id} is zoho_books but has no organization_id"
            )
        return ZohoAdapter(organization_id=connection.zoho_organization_id)
    raise ValueError(f"Unknown books_system: {connection.books_system!r}")
