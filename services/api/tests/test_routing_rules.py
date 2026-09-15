"""
TE-02 routing rules and TE-04 role-aware escalation.

Covers routing on create, escalation to the role above the routine owner,
unknown task_type handling, and that an explicit assignee is never
overridden by the table.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.routing_rule import RoutingRule
from app.models.user import User
from app.task_engine import TaskEngine
from app.task_engine.service import UNROUTED_FALLBACK_ROLE


async def _rule(
    session: AsyncSession, task_type: str, role: str, hours: int = 24
) -> RoutingRule:
    rule = RoutingRule(task_type=task_type, default_role=role, escalate_after_hours=hours)
    session.add(rule)
    await session.flush()
    return rule


async def test_create_task_routes_to_rule_role(session: AsyncSession) -> None:
    """TE-02 — an unassigned task lands on the role its rule names."""
    await _rule(session, "new_ledger_approval", "junior", hours=8)
    engine = TaskEngine(session)

    task = await engine.create_task(task_type="new_ledger_approval")

    assert task.assigned_role == "junior"
    assert task.assignee_id is None  # role-level routing; person left open
    # due_at defaulted from the rule's escalate_after_hours
    assert task.due_at is not None
    assert timedelta(hours=7) < (task.due_at - datetime.now(UTC)) < timedelta(hours=9)


async def test_explicit_assignee_is_not_overridden(session: AsyncSession) -> None:
    """A caller that already knows the assignee is not second-guessed by the table."""
    await _rule(session, "invoice_approval", "proprietor")
    user = User(name="Senior Staff", email="senior@example.com", role="senior", hashed_password="x")
    session.add(user)
    await session.flush()

    engine = TaskEngine(session)
    task = await engine.create_task(task_type="invoice_approval", assignee_id=user.id)

    assert task.assignee_id == user.id
    assert task.assigned_role is None  # routing skipped entirely


async def test_explicit_due_at_is_not_overridden(session: AsyncSession) -> None:
    """An explicit due date wins over the rule's escalate_after_hours default."""
    await _rule(session, "gst_filing_review", "senior", hours=48)
    explicit = datetime.now(UTC) + timedelta(hours=3)

    engine = TaskEngine(session)
    task = await engine.create_task(task_type="gst_filing_review", due_at=explicit)

    assert task.due_at == explicit
    assert task.assigned_role == "senior"


async def test_unknown_task_type_is_not_dropped(session: AsyncSession) -> None:
    """
    An unrouted task must still be created and still be visible to someone —
    ADR 0005's premise is that human-touch items land on a person, not a flag.
    """
    engine = TaskEngine(session)
    task = await engine.create_task(task_type="task_type_with_no_rule")

    assert task.status == "open"
    assert task.assigned_role == UNROUTED_FALLBACK_ROLE == "senior"
    assert task.assigned_role != "proprietor"  # ADR 0005: don't default upward


async def test_escalation_goes_one_role_up(session: AsyncSession) -> None:
    """TE-04 — a junior's overdue task escalates to senior, not the proprietor."""
    await _rule(session, "bank_recon_mismatch", "junior")
    engine = TaskEngine(session)
    task = await engine.create_task(
        task_type="bank_recon_mismatch",
        due_at=datetime.now(UTC) - timedelta(hours=1),
    )
    assert task.assigned_role == "junior"

    escalated = await engine.escalate_overdue()

    assert [t.id for t in escalated] == [task.id]
    assert task.status == "escalated"
    assert task.assigned_role == "senior"


async def test_escalation_from_senior_reaches_proprietor(session: AsyncSession) -> None:
    """TE-04 — the ladder's next step above senior is the proprietor."""
    await _rule(session, "client_comms_approval", "senior")
    engine = TaskEngine(session)
    task = await engine.create_task(
        task_type="client_comms_approval",
        due_at=datetime.now(UTC) - timedelta(hours=1),
    )

    await engine.escalate_overdue()

    assert task.assigned_role == "proprietor"


async def test_escalation_at_proprietor_is_terminal(session: AsyncSession) -> None:
    """There is nobody above the proprietor — escalation must not loop or fail."""
    await _rule(session, "final_signoff", "proprietor")
    engine = TaskEngine(session)
    task = await engine.create_task(
        task_type="final_signoff",
        due_at=datetime.now(UTC) - timedelta(hours=1),
    )

    await engine.escalate_overdue()

    assert task.status == "escalated"
    assert task.assigned_role == "proprietor"


async def test_escalation_preserves_assignee(session: AsyncSession) -> None:
    """Escalation changes accountability but keeps who had been sitting on it (TE-09)."""
    user = User(name="Junior Staff", email="junior@example.com", role="junior", hashed_password="x")
    session.add(user)
    await session.flush()

    engine = TaskEngine(session)
    task = await engine.create_task(
        task_type="anything",
        assignee_id=user.id,
        due_at=datetime.now(UTC) - timedelta(hours=1),
    )

    await engine.escalate_overdue()

    assert task.status == "escalated"
    assert task.assignee_id == user.id


async def test_escalation_of_unrouted_task(session: AsyncSession) -> None:
    """A task with no rule still escalates somewhere rather than erroring."""
    engine = TaskEngine(session)
    task = await engine.create_task(
        task_type="no_rule_for_this",
        due_at=datetime.now(UTC) - timedelta(hours=1),
    )
    assert task.assigned_role == "senior"

    await engine.escalate_overdue()

    assert task.status == "escalated"
    assert task.assigned_role == "proprietor"
