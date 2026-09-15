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

from app.models.routing_rule import RoutingRule
from app.models.task import Task

# TE-04 escalation ladder. A RoutingRule carries one role (the routine
# owner), so the escalation target is derived by moving one step up rather
# than configured separately. This satisfies TE-04's "escalates to senior
# staff or proprietor depending on task type" while honouring ADR 0005's
# requirement that routine work must not default to the proprietor: a
# junior's overdue task reaches a senior first, not the proprietor.
# proprietor is terminal — there is nobody above it.
ESCALATION_LADDER = {"junior": "senior", "senior": "proprietor", "proprietor": "proprietor"}

# Where a task goes when no RoutingRule matches its task_type. ADR 0005's
# whole premise is that a human-touch item must land on a specific person
# rather than becoming a generic flag, so an unrouted task must never be
# dropped or left invisible. It is created as normal and parked with
# senior staff for triage — deliberately not the proprietor, per ADR 0005,
# and deliberately not junior, since an unrecognised task type is a
# configuration gap someone needs to notice and fix.
UNROUTED_FALLBACK_ROLE = "senior"


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
        """
        TE-01 — any agent exception or judgment call creates a task record.

        TE-02 — when no explicit assignee is supplied, the routing rule for
        this task_type decides which role owns it, and supplies the default
        due date from its escalate_after_hours. An explicit assignee_id is
        always respected: a caller that already knows who should handle a
        task is not second-guessed by the table.
        """
        assigned_role: str | None = None
        if assignee_id is None:
            rule = await self._rule_for(task_type)
            if rule is None:
                assigned_role = UNROUTED_FALLBACK_ROLE
            else:
                assigned_role = rule.default_role
                if due_at is None:
                    due_at = in_hours(rule.escalate_after_hours)

        task = Task(
            task_type=task_type,
            client_id=client_id,
            linked_record_type=linked_record_type,
            linked_record_id=linked_record_id,
            due_at=due_at,
            created_by_agent=created_by_agent,
            assignee_id=assignee_id,
            assigned_role=assigned_role,
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
        TE-04 — auto-escalation when a task passes its due date, to the role
        above the one that owned it rather than only flipping status.

        The task's current owning role comes from its RoutingRule (or from
        assigned_role, for a task whose rule has since been deleted), and
        the target is one step up ESCALATION_LADDER. An escalated task keeps
        its assignee_id: escalation changes who is *accountable*, and
        clearing the original assignee would erase who had been sitting on
        it, which is precisely what the audit trail (TE-09) is for.

        Intended to run on a schedule (Celery beat, per ADR 0007).
        """
        now = datetime.now(UTC)
        result = await self.session.execute(
            select(Task).where(Task.status == "open", Task.due_at.is_not(None), Task.due_at < now)
        )
        overdue = list(result.scalars().all())
        for task in overdue:
            task.status = "escalated"
            task.assigned_role = await self._escalation_target(task)
        if overdue:
            await self.session.flush()
        return overdue

    async def _escalation_target(self, task: Task) -> str:
        """The role an overdue task escalates to — one step up the ladder."""
        rule = await self._rule_for(task.task_type)
        current = rule.default_role if rule is not None else task.assigned_role
        if current not in ESCALATION_LADDER:
            # No rule and no recorded role: nothing to step up from, so park
            # it with senior staff for triage rather than leave it ownerless.
            return UNROUTED_FALLBACK_ROLE
        return ESCALATION_LADDER[current]

    async def _rule_for(self, task_type: str) -> RoutingRule | None:
        result = await self.session.execute(
            select(RoutingRule).where(RoutingRule.task_type == task_type)
        )
        return result.scalar_one_or_none()

    async def _get(self, task_id: str) -> Task:
        task = await self.session.get(Task, task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")
        return task
