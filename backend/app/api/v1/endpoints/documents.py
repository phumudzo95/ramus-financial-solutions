"""
Documents Endpoint — upload, list, download, verify documents per application.
Files stored in S3 with encrypted metadata in DB.
"""
from __future__ import annotations
import hashlib
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

import boto3
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.security import get_current_user, require_roles
from app.db.session import get_db
from app.models.models import Document, Application, User, UserRole, AuditAction
from app.audit.audit_service import AuditService
from app.core.exceptions import NotFoundException, AuthorizationException, DocumentStorageException

logger = logging.getLogger(__name__)
router = APIRouter()

ALLOWED_MIME_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/webp"}
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


def get_s3_client():
    return boto3.client("s3", region_name=settings.AWS_REGION)


async def _get_application_or_403(application_id, current_user, db):
    result = await db.execute(select(Application).where(Application.id == application_id))
    app = result.scalar_one_or_none()
    if not app:
        raise NotFoundException(f"Application {application_id} not found")
    if current_user.role == UserRole.CLIENT and app.applicant_id != current_user.id:
        raise AuthorizationException("You do not have access to this application")
    return app


@router.post("/{application_id}/upload", status_code=status.HTTP_201_CREATED)
async def upload_document(
    application_id: uuid.UUID,
    document_type: str = Query(...),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload a document for an application. Stored in S3."""
    await _get_application_or_403(application_id, current_user, db)

    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail=f"File type {file.content_type} not allowed.")

    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 10MB limit")

    checksum = hashlib.sha256(contents).hexdigest()
    s3_key = f"documents/{application_id}/{document_type}/{uuid.uuid4()}/{file.filename}"

    try:
        s3 = get_s3_client()
        s3.put_object(
            Bucket=settings.AWS_S3_BUCKET_DOCUMENTS,
            Key=s3_key,
            Body=contents,
            ContentType=file.content_type,
            ServerSideEncryption="aws:kms",
            SSEKMSKeyId=settings.AWS_KMS_KEY_ID,
        )
    except ClientError as e:
        logger.error("S3 upload failed: %s", e)
        raise DocumentStorageException("Failed to store document. Please try again.")

    doc = Document(
        id=uuid.uuid4(),
        application_id=application_id,
        uploader_id=current_user.id,
        document_type=document_type,
        file_name=file.filename,
        file_size_bytes=len(contents),
        mime_type=file.content_type,
        s3_key=s3_key,
        checksum_sha256=checksum,
        is_verified=False,
    )
    db.add(doc)
    await db.flush()

    audit = AuditService(db)
    await audit.log(
        action=AuditAction.DOCUMENT_UPLOADED,
        actor_id=current_user.id,
        target_type="document",
        target_id=doc.id,
        after_state={"document_type": document_type, "file_name": file.filename},
    )

    return {
        "id": str(doc.id),
        "application_id": str(application_id),
        "document_type": document_type,
        "file_name": file.filename,
        "file_size_bytes": len(contents),
        "is_verified": False,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/{application_id}")
async def list_documents(
    application_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all documents for an application."""
    await _get_application_or_403(application_id, current_user, db)
    result = await db.execute(
        select(Document).where(Document.application_id == application_id)
    )
    docs = result.scalars().all()
    return {
        "items": [
            {
                "id": str(d.id),
                "document_type": d.document_type,
                "file_name": d.file_name,
                "file_size_bytes": d.file_size_bytes,
                "is_verified": d.is_verified,
                "created_at": d.created_at.isoformat(),
            }
            for d in docs
        ],
        "total": len(docs),
    }


@router.get("/{application_id}/{document_id}/download")
async def get_download_url(
    application_id: uuid.UUID,
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a 15-minute pre-signed S3 download URL."""
    await _get_application_or_403(application_id, current_user, db)
    result = await db.execute(
        select(Document).where(Document.id == document_id, Document.application_id == application_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise NotFoundException("Document not found")

    try:
        s3 = get_s3_client()
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.AWS_S3_BUCKET_DOCUMENTS, "Key": doc.s3_key},
            ExpiresIn=900,
        )
    except ClientError as e:
        raise DocumentStorageException("Could not generate download link")

    return {"download_url": url, "expires_in_seconds": 900}


class DocumentVerifyRequest(BaseModel):
    verified: bool
    rejection_reason: Optional[str] = None


@router.patch("/{application_id}/{document_id}/verify")
async def verify_document(
    application_id: uuid.UUID,
    document_id: uuid.UUID,
    body: DocumentVerifyRequest,
    current_user: User = Depends(require_roles([UserRole.WORKER, UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db),
):
    """Worker verifies or rejects a document."""
    result = await db.execute(
        select(Document).where(Document.id == document_id, Document.application_id == application_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise NotFoundException("Document not found")

    doc.is_verified = body.verified
    doc.verified_by_id = current_user.id
    doc.verified_at = datetime.now(timezone.utc)
    doc.rejection_reason = body.rejection_reason
    await db.flush()

    audit = AuditService(db)
    await audit.log(
        action=AuditAction.DOCUMENT_REVIEWED,
        actor_id=current_user.id,
        target_type="document",
        target_id=document_id,
        after_state={"is_verified": body.verified},
    )

    return {"id": str(doc.id), "is_verified": doc.is_verified}
