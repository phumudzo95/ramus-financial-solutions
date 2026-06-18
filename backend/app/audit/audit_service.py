"""
Audit Logging Service — Immutable, append-only compliance audit trail.
Every user action, system action, decision, and external API call is recorded here.
Logs are never updated or deleted. Archived to S3 after AUDIT_S3_ARCHIVE_AFTER_DAYS.
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Any, Optional
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from fastapi import Request

from app.models.models import AuditLog, AuditAction, UserRole

logger = logging.getLogger(__name__)


class AuditService:
    """
    Central audit logging service.
    Usage: inject AuditService into any service that needs to log actions.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def log(
        self,
        action: AuditAction,
        actor_id: Optional[str] = None,
        actor_role: Optional[UserRole] = None,
        actor_ip: Optional[str] = None,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        before_state: Optional[dict] = None,
        after_state: Optional[dict] = None,
        log_metadata: Optional[dict] = None,
        request_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> AuditLog:
        """
        Append an immutable audit record.
        This method must NEVER raise — log errors are caught and swallowed
        so audit failures never interrupt business operations.
        """
        try:
            audit_entry = AuditLog(
                action=action,
                actor_id=uuid.UUID(actor_id) if actor_id else None,
                actor_role=actor_role,
                actor_ip=actor_ip,
                target_type=target_type,
                target_id=uuid.UUID(target_id) if target_id else None,
                before_state=before_state,
                after_state=after_state,
                log_metadata=log_metadata or {},
                request_id=request_id,
                session_id=session_id,
            )
            self.db.add(audit_entry)
            await self.db.flush()
            logger.debug(
                "AUDIT: %s | actor=%s | target=%s/%s | req=%s",
                action.value, actor_id, target_type, target_id, request_id,
            )
            return audit_entry
        except Exception as e:
            # Audit must NEVER break the main flow
            logger.error("Audit log write failed: %s | action=%s", e, action.value, exc_info=True)

    async def log_from_request(
        self,
        request: Request,
        action: AuditAction,
        actor_id: Optional[str] = None,
        actor_role: Optional[UserRole] = None,
        **kwargs,
    ) -> AuditLog:
        """Convenience method that extracts IP and request ID from FastAPI request."""
        ip = request.client.host if request.client else None
        request_id = getattr(request.state, "request_id", None)
        return await self.log(
            action=action,
            actor_id=actor_id,
            actor_role=actor_role,
            actor_ip=ip,
            request_id=request_id,
            **kwargs,
        )

    # ── Query Methods ─────────────────────────────────────────────────────────

    async def get_logs_for_application(
        self, application_id: str, limit: int = 100
    ) -> list[AuditLog]:
        result = await self.db.execute(
            select(AuditLog)
            .where(
                and_(
                    AuditLog.target_type == "application",
                    AuditLog.target_id == uuid.UUID(application_id),
                )
            )
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def get_logs_for_actor(
        self, actor_id: str, limit: int = 200
    ) -> list[AuditLog]:
        result = await self.db.execute(
            select(AuditLog)
            .where(AuditLog.actor_id == uuid.UUID(actor_id))
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def get_logs_by_action(
        self, action: AuditAction, from_dt: Optional[datetime] = None, limit: int = 500
    ) -> list[AuditLog]:
        query = select(AuditLog).where(AuditLog.action == action)
        if from_dt:
            query = query.where(AuditLog.created_at >= from_dt)
        query = query.order_by(AuditLog.created_at.desc()).limit(limit)
        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_decision_logs(
        self, from_dt: Optional[datetime] = None, limit: int = 500
    ) -> list[AuditLog]:
        query = select(AuditLog).where(
            AuditLog.action.in_([AuditAction.DECISION_MADE, AuditAction.DECISION_OVERRIDDEN])
        )
        if from_dt:
            query = query.where(AuditLog.created_at >= from_dt)
        result = await self.db.execute(query.order_by(AuditLog.created_at.desc()).limit(limit))
        return result.scalars().all()

    async def get_bureau_request_logs(
        self, from_dt: Optional[datetime] = None, limit: int = 500
    ) -> list[AuditLog]:
        query = select(AuditLog).where(
            AuditLog.action.in_([
                AuditAction.BUREAU_REQUEST_INITIATED,
                AuditAction.BUREAU_RESPONSE_RECEIVED,
                AuditAction.BUREAU_REQUEST_FAILED,
            ])
        )
        if from_dt:
            query = query.where(AuditLog.created_at >= from_dt)
        result = await self.db.execute(query.order_by(AuditLog.created_at.desc()).limit(limit))
        return result.scalars().all()

    async def get_audit_summary(self) -> dict:
        """Admin dashboard — summary counts of recent audit activity."""
        result = await self.db.execute(
            select(AuditLog.action, func.count(AuditLog.id).label("count"))
            .group_by(AuditLog.action)
        )
        rows = result.all()
        return {row.action.value: row.count for row in rows}


# ── S3 Archive (async background task) ────────────────────────────────────────

class AuditArchiver:
    """
    Archives audit logs older than AUDIT_S3_ARCHIVE_AFTER_DAYS to S3.
    Runs as a daily scheduled task (AWS EventBridge → Lambda or Celery beat).
    Does NOT delete from DB — keeps a reference record.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def archive_old_logs(self) -> dict:
        from datetime import timedelta
        from app.core.config import settings
        import boto3
        import json

        cutoff = datetime.now(timezone.utc) - timedelta(days=settings.AUDIT_S3_ARCHIVE_AFTER_DAYS)
        result = await self.db.execute(
            select(AuditLog).where(AuditLog.created_at < cutoff).limit(1000)
        )
        logs = result.scalars().all()

        if not logs:
            return {"archived": 0}

        s3 = boto3.client("s3", region_name=settings.AWS_REGION)
        batch = [
            {
                "id": str(log.id),
                "action": log.action.value,
                "actor_id": str(log.actor_id) if log.actor_id else None,
                "target_type": log.target_type,
                "target_id": str(log.target_id) if log.target_id else None,
                "created_at": log.created_at.isoformat(),
                "metadata": log.log_metadata,
            }
            for log in logs
        ]

        date_str = datetime.now(timezone.utc).strftime("%Y/%m/%d")
        key = f"audit-archive/{date_str}/batch-{uuid.uuid4()}.json"

        s3.put_object(
            Bucket=settings.AWS_S3_BUCKET_AUDIT_LOGS,
            Key=key,
            Body=json.dumps(batch),
            ServerSideEncryption="aws:kms",
            SSEKMSKeyId=settings.AWS_KMS_KEY_ID,
        )

        logger.info("Archived %d audit logs to s3://%s/%s", len(logs), settings.AWS_S3_BUCKET_AUDIT_LOGS, key)
        return {"archived": len(logs), "s3_key": key}
