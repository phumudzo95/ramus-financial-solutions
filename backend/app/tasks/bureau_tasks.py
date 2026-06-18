"""
Bureau Tasks — Celery async tasks for credit bureau checks.
These run in background workers so API responses are non-blocking.
"""
from __future__ import annotations
import uuid
import logging
from datetime import datetime, timezone

from celery import Celery
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import settings

logger = logging.getLogger(__name__)

# Create sync Celery app (Celery workers are sync by default)
celery_app = Celery(
    "ramus_tasks",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Africa/Johannesburg",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "app.tasks.bureau_tasks.fetch_credit_report": {"queue": "bureau"},
        "app.tasks.bureau_tasks.process_bureau_webhook": {"queue": "bureau"},
    },
)


@celery_app.task(
    bind=True,
    name="app.tasks.bureau_tasks.fetch_credit_report",
    max_retries=3,
    default_retry_delay=60,
    soft_time_limit=120,
    time_limit=180,
)
def fetch_credit_report(
    self,
    snapshot_id: str,
    application_id: str,
    consent_id: str,
    id_number: str,
) -> dict:
    """
    Async Celery task: call TransUnion, store result, trigger decision.
    Retries up to 3 times on failure with 60s delay.
    """
    from app.integrations.credit_bureaus.transunion import TransUnionClient
    from app.models.models import CreditSnapshot, Application, AuditAction
    from app.audit.audit_service import AuditService

    # Use sync DB connection for Celery
    sync_url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    engine = create_engine(sync_url, pool_pre_ping=True)

    with Session(engine) as db:
        try:
            # Mark snapshot as in-progress
            snapshot = db.get(CreditSnapshot, uuid.UUID(snapshot_id))
            if not snapshot:
                logger.error("Snapshot %s not found", snapshot_id)
                return {"status": "error", "reason": "snapshot_not_found"}

            snapshot.status = "fetching"
            db.commit()

            # Call bureau
            client = TransUnionClient()
            bureau_result = client.fetch_credit_report_sync(
                id_number=id_number,
                snapshot_id=snapshot_id,
            )

            # Update snapshot with results
            snapshot.credit_score = bureau_result.get("credit_score")
            snapshot.risk_category = bureau_result.get("risk_category")
            snapshot.total_accounts = bureau_result.get("total_accounts")
            snapshot.open_accounts = bureau_result.get("open_accounts")
            snapshot.closed_accounts = bureau_result.get("closed_accounts")
            snapshot.negative_listings_count = bureau_result.get("negative_listings_count", 0)
            snapshot.judgements_count = bureau_result.get("judgements_count", 0)
            snapshot.defaults_count = bureau_result.get("defaults_count", 0)
            snapshot.total_outstanding_debt = bureau_result.get("total_outstanding_debt")
            snapshot.monthly_obligations = bureau_result.get("monthly_obligations")
            snapshot.oldest_account_months = bureau_result.get("oldest_account_months")
            snapshot.enquiries_last_90_days = bureau_result.get("enquiries_last_90_days", 0)
            snapshot.bureau_request_id = bureau_result.get("bureau_request_id")
            snapshot.status = "success"
            snapshot.received_at = datetime.now(timezone.utc)
            db.commit()

            logger.info(
                "Bureau check complete for snapshot %s — score: %s",
                snapshot_id,
                snapshot.credit_score,
            )

            # Trigger automated decision now that we have bureau data
            run_automated_decision.delay(
                application_id=application_id,
                snapshot_id=snapshot_id,
            )

            return {"status": "success", "snapshot_id": snapshot_id}

        except Exception as exc:
            logger.error("Bureau task failed for snapshot %s: %s", snapshot_id, exc)
            # Update snapshot to failed
            try:
                snapshot = db.get(CreditSnapshot, uuid.UUID(snapshot_id))
                if snapshot:
                    snapshot.status = "failed"
                    snapshot.error_message = str(exc)
                    db.commit()
            except Exception:
                pass

            # Retry
            raise self.retry(exc=exc)


@celery_app.task(
    name="app.tasks.bureau_tasks.run_automated_decision",
    soft_time_limit=60,
)
def run_automated_decision(application_id: str, snapshot_id: str) -> dict:
    """Trigger automated decision engine after bureau data is ready."""
    import asyncio
    from app.services.application_service import ApplicationService
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

    async def _run():
        async_engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
        async_session = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
        async with async_session() as db:
            service = ApplicationService(db)
            decision = await service.run_decision(
                application_id=uuid.UUID(application_id),
                actor_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),  # system actor
                credit_snapshot_id=uuid.UUID(snapshot_id),
            )
            await db.commit()
            return {"outcome": decision.outcome.value, "decision_id": str(decision.id)}

    return asyncio.run(_run())


@celery_app.task(name="app.tasks.bureau_tasks.process_bureau_webhook")
def process_bureau_webhook(payload: dict) -> dict:
    """Process incoming TransUnion webhook — update snapshot from async callback."""
    snapshot_id = payload.get("reference_id")
    if not snapshot_id:
        return {"status": "ignored", "reason": "no_reference_id"}

    sync_url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    engine = create_engine(sync_url, pool_pre_ping=True)

    with Session(engine) as db:
        snapshot = db.get(CreditSnapshot, uuid.UUID(snapshot_id))
        if not snapshot:
            return {"status": "error", "reason": "snapshot_not_found"}

        data = payload.get("data", {})
        snapshot.credit_score = data.get("credit_score", snapshot.credit_score)
        snapshot.status = "success"
        snapshot.received_at = datetime.now(timezone.utc)
        snapshot.bureau_request_id = payload.get("bureau_request_id")
        db.commit()

        # Trigger decision
        run_automated_decision.delay(
            application_id=str(snapshot.application_id),
            snapshot_id=snapshot_id,
        )

    return {"status": "processed", "snapshot_id": snapshot_id}
