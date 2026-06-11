"""
Applications Endpoint — Create, read, update, lifecycle management.
Role-based access:
  - CLIENT: create own, view own
  - WORKER: view assigned, update status, add notes
  - ADMIN: view all, full access
"""
from __future__ import annotations
import random
import string
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func

from app.core.security import get_current_user, require_roles
from app.db.session import get_db
from app.models.models import (
    Application, ApplicationStatus, Decision, User, UserRole,
    WorkflowEvent, AuditAction,
)
from app.audit.audit_service import AuditService
from app.notifications.email_service import EmailNotificationService
from app.core.encryption import EncryptionService

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class ApplicationCreate(BaseModel):
    requested_amount: Decimal = Field(..., gt=0, le=500000, description="Amount in ZAR")
    requested_term_months: int = Field(..., ge=1, le=84)
    loan_purpose: str = Field(..., max_length=100)
    monthly_income: Decimal = Field(..., gt=0)
    monthly_expenses: Decimal = Field(..., ge=0)
    employment_type: str = Field(..., pattern="^(employed|self_employed|contract|pensioner)$")
    employment_duration_months: int = Field(..., ge=0)
    employer_name: Optional[str] = Field(None, max_length=200)


class ApplicationStatusUpdate(BaseModel):
    status: ApplicationStatus
    reason: Optional[str] = Field(None, max_length=500)


class ApplicationResponse(BaseModel):
    id: str
    reference_number: str
    status: ApplicationStatus
    requested_amount: Decimal
    requested_term_months: int
    loan_purpose: str
    employment_type: str
    submitted_at: Optional[datetime]
    created_at: datetime
    assigned_worker_id: Optional[str]

    class Config:
        from_attributes = True


class ApplicationListResponse(BaseModel):
    items: list[ApplicationResponse]
    total: int
    page: int
    per_page: int


# ── Helpers ───────────────────────────────────────────────────────────────────

def generate_reference() -> str:
    chars = string.ascii_uppercase + string.digits
    suffix = "".join(random.choices(chars, k=8))
    return f"RCL-{suffix}"


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("", status_code=status.HTTP_201_CREATED, response_model=ApplicationResponse)
async def create_application(
    payload: ApplicationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Client submits a new loan application."""
    enc = EncryptionService()
    audit = AuditService(db)
    notifier = EmailNotificationService(db)

    app = Application(
        applicant_id=current_user.id,
        reference_number=generate_reference(),
        status=ApplicationStatus.SUBMITTED,
        requested_amount=payload.requested_amount,
        requested_term_months=payload.requested_term_months,
        loan_purpose=payload.loan_purpose,
        employment_type=payload.employment_type,
        employment_duration_months=payload.employment_duration_months,
        monthly_income_enc=enc.encrypt(str(payload.monthly_income)),
        monthly_expenses_enc=enc.encrypt(str(payload.monthly_expenses)),
        employer_name_enc=enc.encrypt(payload.employer_name or ""),
        submitted_at=datetime.now(timezone.utc),
        priority_level=1,
    )
    db.add(app)

    # Initial workflow event
    event = WorkflowEvent(
        application_id=app.id,
        actor_id=current_user.id,
        from_status=None,
        to_status=ApplicationStatus.SUBMITTED,
        reason="Application submitted by client",
    )
    db.add(event)

    await db.commit()
    await db.refresh(app)

    # Audit
    await audit.log(
        action=AuditAction.APPLICATION_CREATED,
        actor_id=str(current_user.id),
        actor_role=current_user.role,
        target_type="application",
        target_id=str(app.id),
        after_state={"reference_number": app.reference_number, "status": app.status.value},
    )

    # Notify client
    first_name = enc.decrypt(current_user.first_name_enc)
    await notifier.notify_application_submitted(
        user_id=str(current_user.id),
        email=current_user.email,
        first_name=first_name,
        reference_number=app.reference_number,
        requested_amount=f"{payload.requested_amount:,.2f}",
        application_id=str(app.id),
    )

    # Trigger auto-assignment workflow
    from app.workflow.engine import WorkflowEngine
    wf = WorkflowEngine(db)
    await wf.auto_assign(app)
    await db.commit()

    return _to_response(app)


@router.get("", response_model=ApplicationListResponse)
async def list_applications(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status_filter: Optional[ApplicationStatus] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List applications.
    - Clients see only their own.
    - Workers see their assigned applications.
    - Admins see everything.
    """
    query = select(Application)

    if current_user.role == UserRole.CLIENT:
        query = query.where(Application.applicant_id == current_user.id)
    elif current_user.role == UserRole.WORKER:
        query = query.where(Application.assigned_worker_id == current_user.id)
    # ADMIN: no filter

    if status_filter:
        query = query.where(Application.status == status_filter)

    count_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = count_result.scalar_one()

    query = query.order_by(Application.created_at.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    apps = result.scalars().all()

    return ApplicationListResponse(
        items=[_to_response(a) for a in apps],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/{application_id}", response_model=ApplicationResponse)
async def get_application(
    application_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    app = await _get_and_authorize(application_id, current_user, db)
    return _to_response(app)


@router.patch("/{application_id}/status", response_model=ApplicationResponse)
async def update_status(
    application_id: str,
    payload: ApplicationStatusUpdate,
    current_user: User = Depends(require_roles([UserRole.WORKER, UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db),
):
    """Worker or admin updates application status."""
    app = await _get_and_authorize(application_id, current_user, db)
    audit = AuditService(db)
    notifier = EmailNotificationService(db)
    enc = EncryptionService()

    old_status = app.status
    app.status = payload.status
    if payload.status in (ApplicationStatus.APPROVED, ApplicationStatus.DECLINED, ApplicationStatus.COMPLETED):
        app.completed_at = datetime.now(timezone.utc)
    if payload.status == ApplicationStatus.UNDER_REVIEW:
        app.reviewed_at = datetime.now(timezone.utc)

    # Workflow event
    event = WorkflowEvent(
        application_id=app.id,
        actor_id=current_user.id,
        from_status=old_status,
        to_status=payload.status,
        reason=payload.reason,
    )
    db.add(event)

    await db.commit()
    await db.refresh(app)

    # Audit
    await audit.log(
        action=AuditAction.APPLICATION_STATUS_CHANGED,
        actor_id=str(current_user.id),
        actor_role=current_user.role,
        target_type="application",
        target_id=str(app.id),
        before_state={"status": old_status.value},
        after_state={"status": payload.status.value},
        metadata={"reason": payload.reason},
    )

    # Email notification to applicant
    applicant_result = await db.execute(select(User).where(User.id == app.applicant_id))
    applicant = applicant_result.scalar_one_or_none()
    if applicant:
        first_name = enc.decrypt(applicant.first_name_enc)
        if payload.status == ApplicationStatus.APPROVED:
            # Find latest decision for amounts
            decision_result = await db.execute(
                select(Decision)
                .where(Decision.application_id == app.id)
                .order_by(Decision.created_at.desc())
                .limit(1)
            )
            decision = decision_result.scalar_one_or_none()
            await notifier.notify_approved(
                user_id=str(applicant.id),
                email=applicant.email,
                first_name=first_name,
                reference_number=app.reference_number,
                approved_amount=f"{decision.approved_amount:,.2f}" if decision and decision.approved_amount else "TBD",
                approved_term_months=decision.approved_term_months if decision else app.requested_term_months,
                approved_rate_percent=str(decision.approved_rate_percent) if decision else "TBD",
                application_id=str(app.id),
            )
        elif payload.status == ApplicationStatus.DECLINED:
            await notifier.notify_declined(
                user_id=str(applicant.id),
                email=applicant.email,
                first_name=first_name,
                reference_number=app.reference_number,
                application_id=str(app.id),
            )
        else:
            await notifier.notify_status_change(
                user_id=str(applicant.id),
                email=applicant.email,
                first_name=first_name,
                reference_number=app.reference_number,
                new_status=payload.status.value,
                application_id=str(app.id),
            )

    return _to_response(app)


@router.post("/{application_id}/run-decision")
async def run_decision_engine(
    application_id: str,
    current_user: User = Depends(require_roles([UserRole.WORKER, UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db),
):
    """
    Trigger the automated decision engine for an application.
    Requires a valid credit snapshot and granted consent.
    """
    from app.services.application_service import ApplicationService
    svc = ApplicationService(db)
    result = await svc.run_decision(application_id, triggered_by=current_user)
    return result


# ── Internal Helpers ──────────────────────────────────────────────────────────

async def _get_and_authorize(
    application_id: str, current_user: User, db: AsyncSession
) -> Application:
    result = await db.execute(
        select(Application).where(Application.id == uuid.UUID(application_id))
    )
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    if current_user.role == UserRole.CLIENT and app.applicant_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    if current_user.role == UserRole.WORKER and app.assigned_worker_id != current_user.id:
        raise HTTPException(status_code=403, detail="Application not assigned to you")

    return app


def _to_response(app: Application) -> ApplicationResponse:
    return ApplicationResponse(
        id=str(app.id),
        reference_number=app.reference_number,
        status=app.status,
        requested_amount=app.requested_amount,
        requested_term_months=app.requested_term_months,
        loan_purpose=app.loan_purpose,
        employment_type=app.employment_type or "",
        submitted_at=app.submitted_at,
        created_at=app.created_at,
        assigned_worker_id=str(app.assigned_worker_id) if app.assigned_worker_id else None,
    )
