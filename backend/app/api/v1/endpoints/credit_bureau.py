"""
Credit Bureau Endpoint — Initiate credit checks, retrieve results.
WORKER and ADMIN only — clients never call this directly.
All calls enforce consent check before hitting the integration layer.
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.core.security import require_roles
from app.db.session import get_db
from app.models.models import (
    AuditAction, BureauProvider, Consent, ConsentPurpose,
    CreditSnapshot, Application, User, UserRole,
)
from app.audit.audit_service import AuditService
from app.core.encryption import EncryptionService

router = APIRouter()


class CreditCheckRequest(BaseModel):
    application_id: str
    bureau_provider: str = "transunion"


@router.post("/check", status_code=status.HTTP_202_ACCEPTED)
async def initiate_credit_check(
    payload: CreditCheckRequest,
    current_user: User = Depends(require_roles([UserRole.WORKER, UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db),
):
    """
    Initiate a credit bureau check for an application.
    Prerequisites:
      1. Application must exist and be assigned/accessible
      2. Applicant must have granted CREDIT_CHECK consent
      3. Bureau credentials must be valid
    All calls are isolated in the integration layer and fully logged.
    """
    enc = EncryptionService()
    audit = AuditService(db)

    # Fetch application
    app_result = await db.execute(
        select(Application).where(Application.id == uuid.UUID(payload.application_id))
    )
    application = app_result.scalar_one_or_none()
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    # Verify worker is assigned (or admin)
    if (current_user.role == UserRole.WORKER and
            application.assigned_worker_id != current_user.id):
        raise HTTPException(status_code=403, detail="Application not assigned to you")

    # MANDATORY: Verify consent exists before any bureau call
    consent_result = await db.execute(
        select(Consent).where(
            and_(
                Consent.user_id == application.applicant_id,
                Consent.application_id == application.id,
                Consent.purpose == ConsentPurpose.CREDIT_CHECK,
                Consent.is_granted == True,
                Consent.revoked_at.is_(None),
            )
        )
    )
    consent = consent_result.scalar_one_or_none()
    if not consent:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Cannot initiate credit check: applicant has not granted "
                "consent for credit bureau access. Consent must be obtained first."
            ),
        )

    # Fetch applicant PII (decrypted in memory only)
    from app.models.models import User as UserModel
    applicant_result = await db.execute(
        select(UserModel).where(UserModel.id == application.applicant_id)
    )
    applicant = applicant_result.scalar_one_or_none()
    if not applicant:
        raise HTTPException(status_code=404, detail="Applicant record not found")

    id_number = enc.decrypt(applicant.id_number_enc) if applicant.id_number_enc else None
    if not id_number:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Applicant ID number not on file. Cannot perform credit check.",
        )

    first_name = enc.decrypt(applicant.first_name_enc)
    last_name = enc.decrypt(applicant.last_name_enc)

    # Create pending snapshot record
    snapshot = CreditSnapshot(
        application_id=application.id,
        consent_id=consent.id,
        bureau_provider=BureauProvider(payload.bureau_provider),
        status="pending",
        requested_at=datetime.now(timezone.utc),
    )
    db.add(snapshot)
    await db.flush()

    # Audit: bureau request initiated
    await audit.log(
        action=AuditAction.BUREAU_REQUEST_INITIATED,
        actor_id=str(current_user.id),
        actor_role=current_user.role,
        target_type="credit_snapshot",
        target_id=str(snapshot.id),
        metadata={
            "bureau_provider": payload.bureau_provider,
            "application_id": payload.application_id,
            "consent_id": str(consent.id),
        },
    )
    await db.commit()

    # Dispatch to integration layer (async via Celery)
    from app.tasks.bureau_tasks import fetch_credit_report_task
    fetch_credit_report_task.delay(
        snapshot_id=str(snapshot.id),
        application_id=str(application.id),
        bureau_provider=payload.bureau_provider,
        id_number=id_number,
        first_name=first_name,
        last_name=last_name,
        consent_id=str(consent.id),
        requested_by=str(current_user.id),
    )

    return {
        "snapshot_id": str(snapshot.id),
        "status": "pending",
        "message": "Credit check initiated. Results will be available shortly.",
        "bureau_provider": payload.bureau_provider,
    }


@router.get("/{application_id}/snapshots")
async def get_credit_snapshots(
    application_id: str,
    current_user: User = Depends(require_roles([UserRole.WORKER, UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve all normalized credit snapshots for an application."""
    result = await db.execute(
        select(CreditSnapshot)
        .where(CreditSnapshot.application_id == uuid.UUID(application_id))
        .order_by(CreditSnapshot.requested_at.desc())
    )
    snapshots = result.scalars().all()

    return {
        "snapshots": [
            {
                "id": str(s.id),
                "bureau_provider": s.bureau_provider.value,
                "status": s.status,
                "credit_score": s.credit_score,
                "risk_category": s.risk_category.value if s.risk_category else None,
                "total_accounts": s.total_accounts,
                "open_accounts": s.open_accounts,
                "negative_listings_count": s.negative_listings_count,
                "judgements_count": s.judgements_count,
                "defaults_count": s.defaults_count,
                "total_outstanding_debt": float(s.total_outstanding_debt) if s.total_outstanding_debt else None,
                "monthly_obligations": float(s.monthly_obligations) if s.monthly_obligations else None,
                "enquiries_last_90_days": s.enquiries_last_90_days,
                "requested_at": s.requested_at.isoformat(),
                "received_at": s.received_at.isoformat() if s.received_at else None,
                "error_code": s.error_code,
                # raw_response_enc intentionally omitted — admin-only via separate endpoint
            }
            for s in snapshots
        ]
    }
