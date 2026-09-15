"""
Task Engine domain errors.

These are deliberately NOT `ApiError`. Per CG8 and ADR 0005 every agent
calls the Task Engine, and agents run in Celery workers, not in a request
— an exception carrying an HTTP status code would be meaningless there and
would couple the shared backbone to one of its callers. The router
translates these into HTTP; nothing else needs to know HTTP exists.

They subclass `ValueError`, which is what the service raised before, so
existing callers that catch `ValueError` keep working. The point of the
subclasses is that a caller can now tell *which* failure happened —
previously a bare `ValueError` made "no such task" and "bad outcome"
indistinguishable, which is exactly why the router could not map them to
different responses.
"""

from __future__ import annotations


class TaskEngineError(ValueError):
    """Base for Task Engine domain failures."""


class TaskNotFoundError(TaskEngineError):
    """No task exists with the given id."""

    def __init__(self, task_id: str) -> None:
        self.task_id = task_id
        super().__init__(f"Task {task_id} not found")


class InvalidOutcomeError(TaskEngineError):
    """
    TE-06 — a task cannot be completed without a recorded outcome from the
    permitted set. ADR 0005 treats this as the enforcement rule, not a
    formatting preference, so it is refused rather than coerced.
    """

    def __init__(self, outcome: str, allowed: tuple[str, ...]) -> None:
        self.outcome = outcome
        self.allowed = allowed
        super().__init__(f"Invalid outcome: {outcome!r}. Must be one of: {', '.join(allowed)}")
