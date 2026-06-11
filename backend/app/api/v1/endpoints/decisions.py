"""
Decisions Endpoint — decision history, manual override, re-run engine.
"""
from __future__ import annotations
import uuid
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.security import get_current_user, require_roles
from app.db.session import get_db
from app.models.models import (
    Decision, Application, User, UserRole,
    DecisionOutcome, RiskCategory, ApplicationStatus, AuditAction,
)
from app.services.application_service import ApplicationService
from app.audit.audit_service import AuditService
from app.core.exceptions import NotFoundException, AuthorizationException

logger = logging.getLogger(__name__)
router = APIRouter()


class DecisionOverrideRequest(BaseModel):
    outcome: str = Field(..., pattern="^(approve|decline)$")
    approved_amount: Optional[Decimal] = Field(None, gt=0)
    approved_term_months: Optional[int] = Field(None, ge=1, le=84)
    approved_rate_percent: Optional[Decimal] = Field(None, gt=0, le=100)
    override_reason: str = Field(..., min_length=20, max_length=1000)


def _serialize_decision(d: Decision) -> dict:
    return {
        "id": str(d.id),
        "application_id": str(d.application_id),
        "is_automated": d.is_automated,
        "outcome": d.outcome.value,
        "risk_category": d.risk_category.value,
        "explanation": d.explanation,
        "rules_applied": d.rules_applied,
        "approved_amount": str(d.approved_amount) if d.approved_amount else None,
        "approved_term_months": d.approved_term_months,
        "approved_rate_percent": str(d.approved_rate_percent) if d.approved_rate_percent else None,
        "is_override": d.is_override,
        "override_reason": d.override_reason,
        "made_by_id": str(d.made_by_id) if d.made_by_id else None,
        "created_at": d.created_at.isoformat(),
    }


# ── Get decisions for an application ─────────────────────────────────────────

@router.get("/application/{application_id}")
async def get_decisions(
    application_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get full decision history for an application."""
    # Check app exists and user has access
    app_result = await db.execute(
        select(Application).where(Application.id == application_id)
    )
    app = app_result.scalar_one_or_none()
    if not app:
        raise NotFoundException("Application not found")
    if current_user.role == UserRole.CLIENT and app.applicant_id != current_user.id:
        raise AuthorizationException("Access denied")

    result = await db.execute(
        select(Decision)
        .where(Decision.application_id == application_id)
        .order_by(Decision.created_at.desc())
    )
    decisions = result.scalars().all()

    return {"items": [_serialize_decision(d) for d in decisions], "total": len(decisions)}


# ── Get single decision ───────────────────────────────────────────────────────

@router.get("/{decision_id}")
async def get_decision(
    decision_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific decision by ID."""
    result = await db.execute(select(Decision).where(Decision.id == decision_id))
    decision = result.scalar_one_or_none()
    if not decision:
        raise NotFoundException("Decision not found")

    # Clients can only see their own application decisions
    if current_user.role == UserRole.CLIENT:
        app_result = await db.execute(
            select(Application).where(Application.id == decision.application_id)
        )
        app = app_result.scalar_one_or_none()
        if not app or app.applicant_id != current_user.id:
            raise AuthorizationException("Access denied")

    return _serialize_decision(decision)


# ── Re-run decision engine ────────────────────────────────────────────────────

@router.post("/application/{application_id}/run")
@require_roles([UserRole.WORKER, UserRole.ADMIN])
async def run_decision(
    application_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger the decision engine for an application."""
    service = ApplicationService(db)
    decision = await service.run_decision(
        application_id=application_id,
        actor_id=current_user.id,
    )
    return _serialize_decision(decision)


# ── Manual override ───────────────────────────────────────────────────────────

@router.post("/application/{application_id}/override")
@require_roles([UserRole.ADMIN])
async def override_decision(
    application_id: uuid.UUID,
    body: DecisionOverrideRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Admin manual override. Creates a new Decision record marked as override.
    Updates application status accordingly.
    """
    app_result = await db.execute(
        select(Application).where(Application.id == application_id)
    )
    app = app_result.scalar_one_or_none()
    if not app:
        raise NotFoundException("Application not found")

    outcome = DecisionOutcome(body.outcome)

    override = Decision(
        id=uuid.uuid4(),
        application_id=application_id,
        made_by_id=current_user.id,
        is_automated=False,
        outcome=outcome,
        risk_category=RiskCategory.MEDIUM,  # human override — use medium as default
        explanation=f"Manual override by admin {current_user.email}: {body.override_reason}",
        rules_applied=[],
        approved_amount=body.approved_amount,
        approved_term_months=body.approved_term_months,
        approved_rate_percent=body.approved_rate_percent,
        is_override=True,
        override_reason=body.override_reason,
    )
    db.add(override)

    old_status = app.status
    app.status = (
        ApplicationStatus.APPROVED if outcome == DecisionOutcome.APPROVE
        else ApplicationStatus.DECLINED
    )
    await db.flush()

    audit = AuditService(db)
    await audit.log(
        action=AuditAction.DECISION_OVERRIDDEN,
        actor_id=current_user.id,
        target_type="application",
        target_id=application_id,
        before_state={"status": old_status.value},
        after_state={"status": app.status.value, "outcome": outcome.value},
        metadata={"override_reason": body.override_reason},
    )

    return _serialize_decision(override)
