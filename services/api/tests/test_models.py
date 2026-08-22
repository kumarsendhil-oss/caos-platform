from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.models.task import Task
from app.models.user import User


async def test_client_and_task_roundtrip(session: AsyncSession) -> None:
    client = Client(
        legal_name="Coastal Components Pvt Ltd",
        entity_type="private_limited",
        books_system="tally",
    )
    session.add(client)
    await session.flush()

    user = User(name="Test Senior", email="senior@example.com", hashed_password="x", role="senior")
    session.add(user)
    await session.flush()

    task = Task(
        task_type="low_confidence_voucher_review",
        client_id=client.id,
        assignee_id=user.id,
        due_at=datetime.now(UTC) + timedelta(hours=12),
        status="open",
        created_by_agent="bookkeeping",
    )
    session.add(task)
    await session.flush()

    assert task.id is not None
    assert task.client_id == client.id
    assert task.status == "open"


async def test_client_books_system_defaults_to_tally(session: AsyncSession) -> None:
    client = Client(legal_name="SR Enterprises", entity_type="proprietorship")
    session.add(client)
    await session.flush()
    assert client.books_system == "tally"


async def test_client_can_be_configured_for_zoho(session: AsyncSession) -> None:
    client = Client(
        legal_name="SR Enterprises", entity_type="proprietorship", books_system="zoho_books"
    )
    session.add(client)
    await session.flush()
    assert client.books_system == "zoho_books"
