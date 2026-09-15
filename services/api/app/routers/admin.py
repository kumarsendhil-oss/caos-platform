"""
Admin endpoints — proprietor-only configuration surfaces.

Currently the TE-02 routing rule table (API spec §4:
GET /admin/routing-rules, PUT /admin/routing-rules/{task_type}).

Role enforcement is server-side per Security Standard §2, which calls out
these endpoints specifically: "the routing rules (TE-02) explicitly assign
some actions ... to the proprietor only; a UI-only restriction would
silently violate that design the moment anyone calls the API directly."
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.errors import ApiError
from app.models.routing_rule import RoutingRule
from app.models.user import ROLES, User
from app.routers.deps import require_role

router = APIRouter(prefix="/admin", tags=["admin"])


class RoutingRuleOut(BaseModel):
    task_type: str
    default_role: str
    escalate_after_hours: int

    model_config = {"from_attributes": True}


class RoutingRuleUpsert(BaseModel):
    """Body of PUT /admin/routing-rules/{task_type}, per API spec §4."""

    default_role: str
    escalate_after_hours: int = Field(gt=0)


@router.get("/routing-rules", response_model=list[RoutingRuleOut])
async def list_routing_rules(
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_role("proprietor")),
) -> list[RoutingRule]:
    """TE-02 — read the routing rule table."""
    result = await session.execute(select(RoutingRule).order_by(RoutingRule.task_type))
    return list(result.scalars().all())


@router.put("/routing-rules/{task_type}", response_model=RoutingRuleOut)
async def upsert_routing_rule(
    task_type: str,
    body: RoutingRuleUpsert,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_role("proprietor")),
) -> RoutingRule:
    """
    TE-02 — create or update the rule for one task type.

    Upsert rather than separate POST/PUT: the API spec defines only PUT
    keyed on task_type, and task_type is unique, so the proprietor editing
    a rule that doesn't exist yet is a create, not a 404.
    """
    if body.default_role not in ROLES:
        raise ApiError(
            "invalid_role",
            f"default_role must be one of: {', '.join(ROLES)}.",
            status_code=422,
        )

    result = await session.execute(select(RoutingRule).where(RoutingRule.task_type == task_type))
    rule = result.scalar_one_or_none()

    if rule is None:
        rule = RoutingRule(task_type=task_type)
        session.add(rule)

    rule.default_role = body.default_role
    rule.escalate_after_hours = body.escalate_after_hours

    await session.commit()
    await session.refresh(rule)
    return rule
