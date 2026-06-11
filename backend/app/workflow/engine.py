"""
Workflow Engine — Application assignment, escalation, and lifecycle management.
Handles: auto-assignment to workers, escalation after SLA breach, priority queue.
"""
from __future__ import annotations
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.models.models import (
    Application, ApplicationStatus, AuditAction,
    User, UserRole, WorkflowEvent,
)
from app.audit.audit_service import AuditService
from app.core.config import settings

logger = logging.getLogger(__name__)


class WorkflowEngine:
    """
    Manages the full application lifecycle:
    - Auto-assigns submitted applications to least-loaded active worker
    - Escalates applications that breach SLA (configurable hours)
    - Tracks all state transitions in workflow_events (immutable)
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.audit = AuditService(db)

    # ── Assignment ────────────────────────────────────────────────────────────

    async def auto_assign(self, application: Application) -> Optional[User]:
        """
        Assign application to the worker with the fewest active assignments.
        Only assigns if WORKFLOW_AUTO_ASSIGN is True.
        Returns the assigned worker or None if no workers available.
        """
        if not settings.WORKFLOW_AUTO_ASSIGN:
            logger.info("Auto-assign disabled — application %s left unassigned", application.id)
            return None

        # Find active workers with fewest open applications
        worker_load_result = await self.db.execute(
            select(
                User.id,
                func.count(Application.id).label("open_count")
            )
            .outerjoin(
                Application,
                and_(
                    Application.assigned_worker_id == User.id,
                    Application.status.in_([
                        ApplicationStatus.SUBMITTED,
                        ApplicationStatus.UNDER_REVIEW,
                        ApplicationStatus.MANUAL_REVIEW,
                    ])
                )
            )
            .where(
                and_(
                    User.role == UserRole.WORKER,
                    User.is_active == True,
                )
            )
            .group_by(User.id)
            .having(func.count(Application.id) < settings.WORKFLOW_MAX_WORKER_QUEUE)
            .order_by(func.count(Application.id).asc())
            .limit(1)
        )
        row = worker_load_result.first()

        if not row:
            logger.warning(
                "No available workers for application %s — all queues full or no active workers",
                application.id,
            )
            return None

        worker_id = row[0]
        old_status = application.status

        application.assigned_worker_id = worker_id
        application.status = ApplicationStatus.UNDER_REVIEW

        event = WorkflowEvent(
            application_id=application.id,
            actor_id=None,  # System action
            from_status=old_status,
            to_status=ApplicationStatus.UNDER_REVIEW,
            reason=f"Auto-assigned to worker by workflow engine",
            metadata={"worker_id": str(worker_id)},
        )
        self.db.add(event)

        await self.audit.log(
            action=AuditAction.APPLICATION_ASSIGNED,
            target_type="application",
            target_id=str(application.id),
            after_state={"assigned_worker_id": str(worker_id), "status": ApplicationStatus.UNDER_REVIEW.value},
            metadata={"assignment_type": "auto"},
        )

        logger.info("Application %s auto-assigned to worker %s", application.id, worker_id)
        return worker_id

    async def manual_assign(
        self,
        application: Application,
        worker_id: str,
        assigned_by: User,
    ) -> User:
        """Manually assign application to a specific worker."""
        worker_result = await self.db.execute(
            select(User).where(
                and_(User.id == uuid.UUID(worker_id), User.role == UserRole.WORKER, User.is_active == True)
            )
        )
        worker = worker_result.scalar_one_or_none()
        if not worker:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Worker not found or inactive")

        old_worker = application.assigned_worker_id
        old_status = application.status

        application.assigned_worker_id = worker.id
        if application.status == ApplicationStatus.SUBMITTED:
            application.status = ApplicationStatus.UNDER_REVIEW

        event = WorkflowEvent(
            application_id=application.id,
            actor_id=assigned_by.id,
            from_status=old_status,
            to_status=application.status,
            reason=f"Manually assigned by {assigned_by.email}",
            metadata={"previous_worker": str(old_worker) if old_worker else None},
        )
        self.db.add(event)

        await self.audit.log(
            action=AuditAction.APPLICATION_ASSIGNED,
            actor_id=str(assigned_by.id),
            actor_role=assigned_by.role,
            target_type="application",
            target_id=str(application.id),
            before_state={"assigned_worker_id": str(old_worker) if old_worker else None},
            after_state={"assigned_worker_id": str(worker.id)},
            metadata={"assignment_type": "manual"},
        )

        return worker

    # ── Escalation ────────────────────────────────────────────────────────────

    async def escalate(
        self,
        application: Application,
        reason: str,
        escalated_by: Optional[User] = None,
    ) -> Application:
        """Escalate an application to admin/senior review."""
        old_status = application.status
        application.status = ApplicationStatus.MANUAL_REVIEW
        application.escalated_at = datetime.now(timezone.utc)
        application.escalation_reason = reason
        application.priority_level = 2  # Escalated = high priority

        event = WorkflowEvent(
            application_id=application.id,
            actor_id=escalated_by.id if escalated_by else None,
            from_status=old_status,
            to_status=ApplicationStatus.MANUAL_REVIEW,
            reason=reason,
            metadata={"escalated_by": str(escalated_by.id) if escalated_by else "system"},
        )
        self.db.add(event)

        await self.audit.log(
            action=AuditAction.APPLICATION_ESCALATED,
            actor_id=str(escalated_by.id) if escalated_by else None,
            actor_role=escalated_by.role if escalated_by else None,
            target_type="application",
            target_id=str(application.id),
            before_state={"status": old_status.value},
            after_state={"status": ApplicationStatus.MANUAL_REVIEW.value},
            metadata={"reason": reason},
        )

        return application

    # ── SLA Breach Check (run by Celery beat) ─────────────────────────────────

    async def check_sla_breaches(self) -> int:
        """
        Find applications that have been in UNDER_REVIEW past the SLA threshold
        and auto-escalate them. Called by Celery beat scheduler.
        """
        sla_cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.WORKFLOW_ESCALATION_HOURS)

        result = await self.db.execute(
            select(Application).where(
                and_(
                    Application.status == ApplicationStatus.UNDER_REVIEW,
                    Application.reviewed_at < sla_cutoff,
                    Application.escalated_at.is_(None),
                )
            )
        )
        breached = result.scalars().all()

        for app in breached:
            await self.escalate(
                application=app,
                reason=f"SLA breach: in review for more than {settings.WORKFLOW_ESCALATION_HOURS} hours",
                escalated_by=None,
            )
            logger.warning(
                "SLA breach escalation: application %s (ref: %s)",
                app.id, app.reference_number,
            )

        if breached:
            await self.db.commit()

        return len(breached)

    # ── Worker Queue Stats ─────────────────────────────────────────────────────

    async def get_worker_queue_stats(self) -> list[dict]:
        """Admin dashboard: per-worker queue depth and status breakdown."""
        result = await self.db.execute(
            select(
                User.id,
                User.email,
                Application.status,
                func.count(Application.id).label("count"),
            )
            .join(Application, Application.assigned_worker_id == User.id)
            .where(User.role == UserRole.WORKER)
            .group_by(User.id, User.email, Application.status)
        )
        rows = result.all()

        stats: dict[str, dict] = {}
        for row in rows:
            wid = str(row.id)
            if wid not in stats:
                stats[wid] = {"worker_id": wid, "email": row.email, "queue": {}}
            stats[wid]["queue"][row.status.value] = row.count

        return list(stats.values())
