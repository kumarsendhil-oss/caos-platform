"""
Task Engine endpoints — GET /tasks, GET /tasks/{id}, POST /tasks/{id}/complete.

Traces to TE-06 (completing a task requires a recorded outcome) and TE-07
(personal My Tasks view), and to Security Standard §2 for the
authentication checks.

NOT covered here, deliberately: completing a task with an INVALID outcome,
and completing a task that does not exist. Both currently return HTTP 500
rather than a 4xx, because TaskEngine.complete raises ValueError and
nothing converts it to an ApiError. Writing a test that asserts 500 would
lock in the bug, so those cases are reported instead — see the PR.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.client import Client
from app.models.task import Task
from app.models.user import User
from app.routers.auth import create_access_token
from app.task_engine import TaskEngine

TASKS = "/api/v1/tasks"


@pytest.fixture
async def auth(session: AsyncSession) -> dict[str, str]:
    user = User(
        name="Senior Staff",
        email="senior@example.com",
        role="senior",
        hashed_password="not-exercised-here",
    )
    session.add(user)
    await session.flush()
    token, _ = create_access_token(user)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def assignee(session: AsyncSession) -> User:
    user = User(
        name="Junior Staff",
        email="junior@example.com",
        role="junior",
        hashed_password="not-exercised-here",
    )
    session.add(user)
    await session.flush()
    return user


@pytest.fixture
async def acme(session: AsyncSession) -> Client:
    client_row = Client(legal_name="Acme Traders Pvt Ltd", entity_type="company")
    session.add(client_row)
    await session.flush()
    return client_row


# --- GET /tasks (TE-07) --------------------------------------------------


async def test_list_tasks_unfiltered_returns_all(
    client: AsyncClient, session: AsyncSession, auth: dict[str, str]
) -> None:
    engine = TaskEngine(session)
    await engine.create_task(task_type="first")
    await engine.create_task(task_type="second")

    response = await client.get(TASKS, headers=auth)

    assert response.status_code == 200
    assert {t["task_type"] for t in response.json()} == {"first", "second"}


async def test_list_tasks_filters_by_assignee(
    client: AsyncClient, session: AsyncSession, auth: dict[str, str], assignee: User
) -> None:
    engine = TaskEngine(session)
    mine = await engine.create_task(task_type="mine", assignee_id=assignee.id)
    await engine.create_task(task_type="someone_elses")

    response = await client.get(TASKS, params={"assignee_id": assignee.id}, headers=auth)

    assert response.status_code == 200
    assert [t["id"] for t in response.json()] == [mine.id]


async def test_list_tasks_filters_by_client(
    client: AsyncClient, session: AsyncSession, auth: dict[str, str], acme: Client
) -> None:
    engine = TaskEngine(session)
    theirs = await engine.create_task(task_type="acme_work", client_id=acme.id)
    await engine.create_task(task_type="unrelated")

    response = await client.get(TASKS, params={"client_id": acme.id}, headers=auth)

    assert response.status_code == 200
    assert [t["id"] for t in response.json()] == [theirs.id]


async def test_list_tasks_filters_by_status(
    client: AsyncClient, session: AsyncSession, auth: dict[str, str]
) -> None:
    engine = TaskEngine(session)
    await engine.create_task(task_type="still_open")
    overdue = await engine.create_task(
        task_type="went_overdue", due_at=datetime.now(UTC) - timedelta(hours=1)
    )
    await engine.escalate_overdue()

    response = await client.get(TASKS, params={"status": "escalated"}, headers=auth)

    assert response.status_code == 200
    assert [t["id"] for t in response.json()] == [overdue.id]
    assert response.json()[0]["status"] == "escalated"


async def test_list_tasks_combines_filters(
    client: AsyncClient,
    session: AsyncSession,
    auth: dict[str, str],
    assignee: User,
    acme: Client,
) -> None:
    """Filters narrow together, not independently."""
    engine = TaskEngine(session)
    both = await engine.create_task(
        task_type="both", assignee_id=assignee.id, client_id=acme.id
    )
    await engine.create_task(task_type="only_assignee", assignee_id=assignee.id)
    await engine.create_task(task_type="only_client", client_id=acme.id)

    response = await client.get(
        TASKS, params={"assignee_id": assignee.id, "client_id": acme.id}, headers=auth
    )

    assert [t["id"] for t in response.json()] == [both.id]


async def test_list_tasks_returns_empty_when_nothing_matches(
    client: AsyncClient, session: AsyncSession, auth: dict[str, str]
) -> None:
    await TaskEngine(session).create_task(task_type="something")

    response = await client.get(TASKS, params={"status": "completed"}, headers=auth)

    assert response.status_code == 200
    assert response.json() == []


# --- GET /tasks/{id} -----------------------------------------------------


async def test_get_task_returns_the_task(
    client: AsyncClient, session: AsyncSession, auth: dict[str, str], acme: Client
) -> None:
    task = await TaskEngine(session).create_task(
        task_type="low_confidence_voucher_review",
        client_id=acme.id,
        created_by_agent="bookkeeping",
    )

    response = await client.get(f"{TASKS}/{task.id}", headers=auth)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == task.id
    assert body["task_type"] == "low_confidence_voucher_review"
    assert body["client_id"] == acme.id
    assert body["created_by_agent"] == "bookkeeping"
    assert body["status"] == "open"


async def test_get_task_404s_for_a_task_that_does_not_exist(
    client: AsyncClient, auth: dict[str, str]
) -> None:
    response = await client.get(f"{TASKS}/no-such-task-id", headers=auth)

    assert response.status_code == 404
    assert response.json()["error_code"] == "task_not_found"


# --- POST /tasks/{id}/complete (TE-06) -----------------------------------


@pytest.mark.parametrize("outcome", ["approved", "rejected", "edited"])
async def test_complete_task_records_each_valid_outcome(
    client: AsyncClient, session: AsyncSession, auth: dict[str, str], outcome: str
) -> None:
    """TE-06 — the outcome is recorded, not just 'marked done'."""
    task = await TaskEngine(session).create_task(task_type="needs_review")

    response = await client.post(
        f"{TASKS}/{task.id}/complete", json={"outcome": outcome}, headers=auth
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["outcome"] == outcome


async def test_completion_is_persisted_not_just_returned(
    client: AsyncClient, session: AsyncSession, auth: dict[str, str]
) -> None:
    """The response is not enough — the row itself must carry the outcome."""
    task = await TaskEngine(session).create_task(task_type="needs_review")

    await client.post(
        f"{TASKS}/{task.id}/complete", json={"outcome": "approved"}, headers=auth
    )

    stored = await session.get(Task, task.id)
    assert stored is not None
    assert stored.status == "completed"
    assert stored.outcome == "approved"


async def test_complete_task_requires_an_outcome_field(
    client: AsyncClient, session: AsyncSession, auth: dict[str, str]
) -> None:
    """TE-06 — an empty body is rejected by the request model, before the engine."""
    task = await TaskEngine(session).create_task(task_type="needs_review")

    response = await client.post(f"{TASKS}/{task.id}/complete", json={}, headers=auth)

    assert response.status_code == 422


# --- Security Standard §2 — every endpoint rejects anonymous callers -----


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("get", TASKS, None),
        ("get", f"{TASKS}/any-id", None),
        ("post", f"{TASKS}/any-id/complete", {"outcome": "approved"}),
    ],
)
async def test_endpoints_reject_unauthenticated_requests(
    client: AsyncClient, method: str, path: str, body: dict[str, str] | None
) -> None:
    response = await getattr(client, method)(path, **({"json": body} if body else {}))

    assert response.status_code in (401, 403)


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("get", TASKS, None),
        ("get", f"{TASKS}/any-id", None),
        ("post", f"{TASKS}/any-id/complete", {"outcome": "approved"}),
    ],
)
async def test_endpoints_reject_a_bad_token(
    client: AsyncClient, method: str, path: str, body: dict[str, str] | None
) -> None:
    """A token is not merely required — it has to verify. Security Standard §2."""
    headers = {"Authorization": "Bearer not-a-real-token"}
    kwargs: dict[str, object] = {"headers": headers}
    if body:
        kwargs["json"] = body

    response = await getattr(client, method)(path, **kwargs)

    assert response.status_code == 401
    assert response.json()["error_code"] == "invalid_token"


def test_jwt_settings_are_sane() -> None:
    """Guards the assumption the token tests rest on."""
    assert settings.jwt_expiry_hours > 0
    assert settings.jwt_algorithm.startswith("HS")
