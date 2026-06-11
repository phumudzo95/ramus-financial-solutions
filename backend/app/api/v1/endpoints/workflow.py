"""
Workflow Endpoint — worker queue management, assignment, escalation, SLA tracking.
"""
from __future__ import annotations
import uuid
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.security import get_current_user, require_roles
from app.db.session import get_db
from app.models.models import (
    Application, ApplicationStatus, WorkflowEvent,
    User, UserRole, AuditAction,
)
from app.workflow.engine import WorkflowEngine
from app.audit.audit_service import AuditService
from app.core.exceptions import NotFoundException, WorkflowException

logger = logging.getLogger(__name__)
router = APIRouter()


class AssignRequest(BaseModel):
    application_id: uuid.UUID
    worker_id: uuid.UUID


class EscalateRequest(BaseModel):
    application_id: uuid.UUID
    reason: str


@router.get("/my-queue")
@require_roles([UserRole.WORKER, UserRole.ADMIN])
async def get_my_queue(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all applications assigned to the current worker."""
    result = await db.execute(
        select(Application)
        .where(
            Application.assigned_worker_id == current_user.id,
            Application.status.in_([
                ApplicationStatus.UNDER_REVIEW,
                ApplicationStatus.MANUAL_REVIEW,
            ])
        )
        .order_by(Application.submitted_at.asc())
    )
    apps = result.scalars().all()
    return {
        "worker_id": str(current_user.id),
        "worker_name": f"{current_user.first_name} {current_user.last_name}",
        "assigned_count": len(apps),
        "queue_items": [
            {
                "id": str(a.id),
                "reference_number": a.reference_number,
                "status": a.status.value,
                "requested_amount": str(a.requested_amount),
                "submitted_at": a.submitted_at.isoformat() if a.submitted_at else None,
            }
            for a in apps
        ],
    }


@router.get("/queue-stats")
@require_roles([UserRole.ADMIN])
async def get_queue_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get queue statistics across all workers."""
    counts = {}
    for s in [ApplicationStatus.SUBMITTED, ApplicationStatus.UNDER_REVIEW, ApplicationStatus.MANUAL_REVIEW]:
        count_result = await db.execute(select(func.count()).where(Application.status == s))
        counts[s.value] = count_result.scalar()

    worker_result = await db.execute(
        select(User).where(User.role == UserRole.WORKER, User.is_active == True)
    )
    workers = worker_result.scalars().all()
    worker_loads = []
    for w in workers:
        count_result = await db.execute(
            select(func.count()).where(
                Application.assigned_worker_id == w.id,
                Application.status.in_([ApplicationStatus.UNDER_REVIEW, ApplicationStatus.MANUAL_REVIEW])
            )
        )
        worker_loads.append({
            "worker_id": str(w.id),
            "worker_name": f"{w.first_name} {w.last_name}",
            "assigned_count": count_result.scalar(),
        })

    return {"queue_counts": counts, "worker_loads": worker_loads, "total_workers": len(workers)}


@router.post("/assign")
@require_roles([UserRole.ADMIN])
async def assign_application(
    body: AssignRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Admin manually assigns an application to a specific worker."""
    app_result = await db.execute(select(Application).where(Application.id == body.application_id))
    app = app_result.scalar_one_or_none()
    if not app:
        raise NotFoundException("Application not found")

    worker_result = await db.execute(
        select(User).where(User.id == body.worker_id, User.role == UserRole.WORKER)
    )
    worker = worker_result.scalar_one_or_none()
    if not worker:
        raise NotFoundException("Worker not found")

    old_status = app.status
    app.assigned_worker_id = body.worker_id
    app.status = ApplicationStatus.UNDER_REVIEW
    await db.flush()

    event = WorkflowEvent(
        id=uuid.uuid4(),
        application_id=body.application_id,
        actor_id=current_user.id,
        from_status=old_status,
        to_status=ApplicationStatus.UNDER_REVIEW,
        reason=f"Assigned to worker {worker.first_name} {worker.last_name}",
    )
    db.add(event)

    audit = AuditService(db)
    await audit.log(
        action=AuditAction.APPLICATION_ASSIGNED,
        actor_id=current_user.id,
        target_type="application",
        target_id=body.application_id,
        after_state={"assigned_worker_id": str(body.worker_id)},
    )

    return {"application_id": str(body.application_id), "assigned_to": str(body.worker_id),
            "worker_name": f"{worker.first_name} {worker.last_name}"}


@router.post("/auto-assign/{application_id}")
@require_roles([UserRole.WORKER, UserRole.ADMIN])
async def auto_assign(
    application_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Auto-assign an application to the least-loaded active worker."""
    engine = WorkflowEngine(db)
    worker = await engine.assign_application(application_id)
    if not worker:
        raise WorkflowException("No available workers to assign to")
    return {"application_id": str(application_id), "assigned_to": str(worker)}


@router.post("/escalate")
@require_roles([UserRole.WORKER, UserRole.ADMIN])
async def escalate_application(
    body: EscalateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Escalate an application for senior review."""
    app_result = await db.execute(select(Application).where(Application.id == body.application_id))
    app = app_result.scalar_one_or_none()
    if not app:
        raise NotFoundException("Application not found")

    old_status = app.status
    app.escalated_at = datetime.now(timezone.utc)
    app.escalation_reason = body.reason

    event = WorkflowEvent(
        id=uuid.uuid4(),
        application_id=body.application_id,
        actor_id=current_user.id,
        from_status=old_status,
        to_status=old_status,
        reason=f"Escalated: {body.reason}",
    )
    db.add(event)

    audit = AuditService(db)
    await audit.log(
        action=AuditAction.APPLICATION_ESCALATED,
        actor_id=current_user.id,
        target_type="application",
        target_id=body.application_id,
        metadata={"reason": body.reason},
    )

    return {"status": "escalated", "application_id": str(body.application_id)}
