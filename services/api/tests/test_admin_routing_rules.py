"""
GET/PUT /admin/routing-rules (API spec §4, TE-02).

Role enforcement is the point of these tests: Security Standard §2 calls
out the routing rules specifically as a case where a UI-only restriction
"would silently violate that design the moment anyone calls the API
directly", so a non-proprietor must be rejected by the endpoint itself.
"""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.routers.auth import create_access_token

BASE = "/api/v1/admin/routing-rules"


async def _user_with_token(session: AsyncSession, role: str) -> tuple[User, dict[str, str]]:
    user = User(
        name=f"{role.title()} User",
        email=f"{role}@example.com",
        role=role,
        hashed_password="x",
    )
    session.add(user)
    await session.flush()
    token, _ = create_access_token(user)
    return user, {"Authorization": f"Bearer {token}"}


async def test_proprietor_can_upsert_and_list(
    client: AsyncClient, session: AsyncSession
) -> None:
    _, headers = await _user_with_token(session, "proprietor")

    created = await client.put(
        f"{BASE}/new_ledger_approval",
        json={"default_role": "junior", "escalate_after_hours": 8},
        headers=headers,
    )
    assert created.status_code == 200
    assert created.json() == {
        "task_type": "new_ledger_approval",
        "default_role": "junior",
        "escalate_after_hours": 8,
    }

    listed = await client.get(BASE, headers=headers)
    assert listed.status_code == 200
    assert listed.json() == [
        {"task_type": "new_ledger_approval", "default_role": "junior", "escalate_after_hours": 8}
    ]


async def test_put_is_an_upsert_not_a_duplicate(
    client: AsyncClient, session: AsyncSession
) -> None:
    """task_type is unique — editing an existing rule must update, not collide."""
    _, headers = await _user_with_token(session, "proprietor")

    await client.put(
        f"{BASE}/gst_filing_review",
        json={"default_role": "junior", "escalate_after_hours": 24},
        headers=headers,
    )
    updated = await client.put(
        f"{BASE}/gst_filing_review",
        json={"default_role": "senior", "escalate_after_hours": 48},
        headers=headers,
    )

    assert updated.status_code == 200
    assert updated.json()["default_role"] == "senior"

    listed = await client.get(BASE, headers=headers)
    assert len(listed.json()) == 1  # updated in place, not duplicated


async def test_senior_is_rejected_server_side(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Security Standard §2 — enforcement is in the endpoint, not the UI."""
    _, headers = await _user_with_token(session, "senior")

    listed = await client.get(BASE, headers=headers)
    assert listed.status_code == 403

    attempted = await client.put(
        f"{BASE}/invoice_approval",
        json={"default_role": "junior", "escalate_after_hours": 4},
        headers=headers,
    )
    assert attempted.status_code == 403


async def test_junior_is_rejected_server_side(
    client: AsyncClient, session: AsyncSession
) -> None:
    _, headers = await _user_with_token(session, "junior")
    assert (await client.get(BASE, headers=headers)).status_code == 403


async def test_unauthenticated_is_rejected(client: AsyncClient) -> None:
    assert (await client.get(BASE)).status_code == 403


async def test_invalid_role_is_rejected(client: AsyncClient, session: AsyncSession) -> None:
    """default_role must be one of the real roles, not arbitrary text."""
    _, headers = await _user_with_token(session, "proprietor")

    response = await client.put(
        f"{BASE}/some_task",
        json={"default_role": "manager", "escalate_after_hours": 8},
        headers=headers,
    )
    assert response.status_code == 422


async def test_non_positive_escalation_window_is_rejected(
    client: AsyncClient, session: AsyncSession
) -> None:
    """A zero or negative window would make every task instantly overdue."""
    _, headers = await _user_with_token(session, "proprietor")

    response = await client.put(
        f"{BASE}/some_task",
        json={"default_role": "senior", "escalate_after_hours": 0},
        headers=headers,
    )
    assert response.status_code == 422
