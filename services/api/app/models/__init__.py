"""
SQLAlchemy models for the core-platform entities, per
audit-platform-ER-core.mermaid (v0.2).

Import order matters for Alembic's autogenerate to see every table —
import every model module here.
"""

from app.models.audit_event import AuditEvent
from app.models.books_connection import BooksConnection
from app.models.client import Client
from app.models.document import Document, ExtractedData
from app.models.email_sender_map import EmailSenderMap
from app.models.task import Task
from app.models.user import User
from app.models.vendor_mapping import VendorMapping
from app.models.voucher import Voucher

__all__ = [
    "AuditEvent",
    "BooksConnection",
    "Client",
    "Document",
    "ExtractedData",
    "EmailSenderMap",
    "Task",
    "User",
    "VendorMapping",
    "Voucher",
]
