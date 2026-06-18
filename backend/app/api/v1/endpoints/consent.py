"""
Consent Endpoint — Explicit consent management.
No credit bureau request may be made without a valid, recorded consent.
Consent records are immutable — never updated or deleted.
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.models import AuditAction, Consent, ConsentPurpose, User
from app.audit.audit_service import AuditService

router = APIRouter()

# Current consent text version — bump when text changes to require re-consent
CONSENT_TEXT_VERSION = "1.0.0"

CONSENT_TEXTS = {
    ConsentPurpose.CREDIT_CHECK: (
        "I authorise Ramus Financial Solutions, a registered credit provider "
        "(NCR Registration: NCRCP19178), to request my credit report and credit "
        "score from TransUnion Credit Bureau and/or any other registered credit bureau "
        "for the purpose of assessing my loan application. I understand that this "
        "enquiry will be recorded on my credit profile. This consent is valid for "
        "the duration of my current loan application."
    ),
    ConsentPurpose.AFFORDABILITY_ASSESSMENT: (
        "I authorise Ramus Financial Solutions to use my provided financial "
        "information to conduct an affordability assessment as required by the "
        "National Credit Act, 34 of 2005."
    ),
}


class ConsentGrantRequest(BaseModel):
    application_id: str
    purpose: ConsentPurpose
    is_granted: bool = Field(..., description="Must be True to proceed")


class ConsentResponse(BaseModel):
    id: str
    purpose: str
    is_granted: bool
    consent_text: str
    consent_text_version: str
    granted_at: str | None
    application_id: str | None


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ConsentResponse)
async def grant_consent(
    payload: ConsentGrantRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Record explicit user consent for credit bureau access.
    Must be called before any bureau request is initiated.
    is_granted must be True — clients cannot be force-enrolled.
    """
    if not payload.is_granted:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Consent must be explicitly granted. If you do not consent, we cannot process your application.",
        )

    # Verify application belongs to current user
    from app.models.models import Application
    app_result = await db.execute(
        select(Application).where(
            and_(
                Application.id == uuid.UUID(payload.application_id),
                Application.applicant_id == current_user.id,
            )
        )
    )
    application = app_result.scalar_one_or_none()
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    # Check for existing active consent for this purpose
    existing = await db.execute(
        select(Consent).where(
            and_(
                Consent.user_id == current_user.id,
                Consent.application_id == application.id,
                Consent.purpose == payload.purpose,
                Consent.is_granted == True,
                Consent.revoked_at.is_(None),
            )
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Consent for this purpose has already been granted for this application.",
        )

    consent_text = CONSENT_TEXTS.get(payload.purpose, "Consent to process your application.")

    consent = Consent(
        user_id=current_user.id,
        application_id=application.id,
        purpose=payload.purpose,
        consent_text=consent_text,
        consent_text_version=CONSENT_TEXT_VERSION,
        is_granted=True,
        granted_at=datetime.now(timezone.utc),
        ip_address=request.client.host if request.client else "unknown",
        user_agent=request.headers.get("user-agent", ""),
    )
    db.add(consent)
    await db.commit()
    await db.refresh(consent)

    audit = AuditService(db)
    await audit.log_from_request(
        request=request,
        action=AuditAction.CONSENT_GRANTED,
        actor_id=str(current_user.id),
        actor_role=current_user.role,
        target_type="consent",
        target_id=str(consent.id),
        after_state={
            "purpose": payload.purpose.value,
            "application_id": str(application.id),
            "version": CONSENT_TEXT_VERSION,
        },
    )

    return ConsentResponse(
        id=str(consent.id),
        purpose=consent.purpose.value,
        is_granted=consent.is_granted,
        consent_text=consent.consent_text,
        consent_text_version=consent.consent_text_version,
        granted_at=consent.granted_at.isoformat() if consent.granted_at else None,
        application_id=str(consent.application_id) if consent.application_id else None,
    )


@router.get("/{application_id}")
async def get_consent_status(
    application_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Check which consents have been granted for an application."""
    result = await db.execute(
        select(Consent).where(
            and_(
                Consent.application_id == uuid.UUID(application_id),
                Consent.user_id == current_user.id,
            )
        )
    )
    consents = result.scalars().all()
    return {
        "consents": [
            {
                "id": str(c.id),
                "purpose": c.purpose.value,
                "is_granted": c.is_granted,
                "granted_at": c.granted_at.isoformat() if c.granted_at else None,
                "revoked_at": c.revoked_at.isoformat() if c.revoked_at else None,
            }
            for c in consents
        ]
    }
