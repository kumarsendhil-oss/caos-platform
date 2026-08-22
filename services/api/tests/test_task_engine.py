from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.task_engine import TaskEngine


async def test_create_task(session: AsyncSession) -> None:
    """TE-01 — any agent exception or judgment call creates a task record."""
    engine = TaskEngine(session)
    task = await engine.create_task(
        task_type="low_confidence_voucher_review",
        due_at=datetime.now(UTC) + timedelta(hours=12),
        created_by_agent="bookkeeping",
    )
    assert task.status == "open"
    assert task.task_type == "low_confidence_voucher_review"


async def test_complete_task_requires_valid_outcome(session: AsyncSession) -> None:
    """TE-06 — completing a task requires a recorded outcome, not just 'marked done'."""
    engine = TaskEngine(session)
    task = await engine.create_task(task_type="test_task")

    with pytest.raises(ValueError, match="Invalid outcome"):
        await engine.complete(task.id, "marked_done")  # not a valid outcome

    completed = await engine.complete(task.id, "approved")
    assert completed.status == "completed"
    assert completed.outcome == "approved"


async def test_escalate_overdue_tasks(session: AsyncSession) -> None:
    """TE-04 — auto-escalation when a task passes its due date."""
    engine = TaskEngine(session)
    overdue_task = await engine.create_task(
        task_type="test_overdue",
        due_at=datetime.now(UTC) - timedelta(hours=1),
    )
    future_task = await engine.create_task(
        task_type="test_future",
        due_at=datetime.now(UTC) + timedelta(hours=1),
    )

    escalated = await engine.escalate_overdue()
    escalated_ids = {t.id for t in escalated}

    assert overdue_task.id in escalated_ids
    assert future_task.id not in escalated_ids
    assert overdue_task.status == "escalated"
    assert future_task.status == "open"


async def test_reassign_task(session: AsyncSession) -> None:
    """TE-03 — manual reassignment available to senior staff and proprietor."""
    engine = TaskEngine(session)
    task = await engine.create_task(task_type="test_task")
    reassigned = await engine.reassign(task.id, "new-assignee-id")
    assert reassigned.assignee_id == "new-assignee-id"
