"""Task Engine (TE) endpoints. Traces to TE-01, TE-03, TE-06, TE-07."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.errors import ApiError
from app.models.task import Task
from app.models.user import User
from app.routers.deps import get_current_user
from app.task_engine import InvalidOutcomeError, TaskEngine, TaskNotFoundError

router = APIRouter(prefix="/tasks", tags=["tasks"])


class TaskOut(BaseModel):
    id: str
    task_type: str
    client_id: str | None
    assignee_id: str | None
    due_at: datetime | None
    status: str
    outcome: str | None
    created_by_agent: str | None

    model_config = {"from_attributes": True}


class TaskUpdateRequest(BaseModel):
    status: str | None = None
    assignee_id: str | None = None
    outcome: str | None = None


class TaskCompleteRequest(BaseModel):
    outcome: str


@router.get("", response_model=list[TaskOut])
async def list_tasks(
    assignee_id: str | None = None,
    client_id: str | None = None,
    status: str | None = None,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> list[Task]:
    """TE-07 — personal My Tasks view, filterable."""
    stmt = select(Task)
    if assignee_id:
        stmt = stmt.where(Task.assignee_id == assignee_id)
    if client_id:
        stmt = stmt.where(Task.client_id == client_id)
    if status:
        stmt = stmt.where(Task.status == status)
    result = await session.execute(stmt.order_by(Task.due_at))
    return list(result.scalars().all())


@router.get("/{task_id}", response_model=TaskOut)
async def get_task(
    task_id: str,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> Task:
    task = await session.get(Task, task_id)
    if task is None:
        raise ApiError(
            "task_not_found", "Task does not exist or you don't have access.", status_code=404
        )
    return task


@router.post("/{task_id}/complete", response_model=TaskOut)
async def complete_task(
    task_id: str,
    body: TaskCompleteRequest,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> Task:
    """
    TE-06 — completing a task requires a recorded outcome.

    The Task Engine raises domain errors, not HTTP ones — agents call it
    too, per CG8 — so translating them into responses is this layer's job.
    Note the not-found case returns exactly what GET /tasks/{id} returns
    for the same condition; the two used to disagree.
    """
    engine = TaskEngine(session)
    try:
        task = await engine.complete(task_id, body.outcome)
    except InvalidOutcomeError as exc:
        raise ApiError(
            "invalid_outcome",
            f"Outcome must be one of: {', '.join(exc.allowed)}.",
            status_code=422,
            detail=f"Received {exc.outcome!r}.",
        ) from exc
    except TaskNotFoundError as exc:
        raise ApiError(
            "task_not_found",
            "Task does not exist or you don't have access.",
            status_code=404,
        ) from exc
    await session.commit()
    return task
