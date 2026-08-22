"""
Task Engine service — the shared backbone every agent writes to instead
of its own notification channel, per ADR 0005. Traces to TE-01, TE-03,
TE-04, TE-05, TE-06.

Per CG8: every agent module should call TaskEngine.create_task(...)
rather than sending its own email/notification or writing its own
"pending review" flag.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task


def in_hours(hours: int) -> datetime:
    return datetime.now(UTC) + timedelta(hours=hours)


class TaskEngine:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_task(
        self,
        *,
        task_type: str,
        client_id: str | None = None,
        linked_record_type: str | None = None,
        linked_record_id: str | None = None,
        due_at: datetime | None = None,
        created_by_agent: str | None = None,
        assignee_id: str | None = None,
    ) -> Task:
        """TE-01 — any agent exception or judgment call creates a task record."""
        task = Task(
            task_type=task_type,
            client_id=client_id,
            linked_record_type=linked_record_type,
            linked_record_id=linked_record_id,
            due_at=due_at,
            created_by_agent=created_by_agent,
            assignee_id=assignee_id,
            status="open",
        )
        self.session.add(task)
        await self.session.flush()
        return task

    async def reassign(self, task_id: str, new_assignee_id: str) -> Task:
        """TE-03 — manual reassignment, available to senior staff and proprietor."""
        task = await self._get(task_id)
        task.assignee_id = new_assignee_id
        await self.session.flush()
        return task

    async def complete(self, task_id: str, outcome: str) -> Task:
        """TE-06 — completing a task requires a recorded outcome, not just 'marked done'."""
        if outcome not in ("approved", "rejected", "edited"):
            raise ValueError(f"Invalid outcome: {outcome!r}")
        task = await self._get(task_id)
        task.status = "completed"
        task.outcome = outcome
        await self.session.flush()
        return task

    async def escalate_overdue(self) -> list[Task]:
        """
        TE-04 — auto-escalation when a task passes its due date.

        Intended to run on a schedule (Celery beat, per ADR 0007).

        STUB(PENDING:007): routing to a specific senior/proprietor by
        task_type is TE-02's routing rule table, not yet built (Sprint
        1-2 deliverable). This currently just flips status so the
        mechanism exists to build tests against. See docs/STUB_ISSUES.md.
        """
        now = datetime.now(UTC)
        result = await self.session.execute(
            select(Task).where(Task.status == "open", Task.due_at.is_not(None), Task.due_at < now)
        )
        overdue = list(result.scalars().all())
        for task in overdue:
            task.status = "escalated"
        if overdue:
            await self.session.flush()
        return overdue

    async def _get(self, task_id: str) -> Task:
        task = await self.session.get(Task, task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")
        return task
