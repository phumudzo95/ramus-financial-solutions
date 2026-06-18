"""
Webhooks Endpoint — receives async callbacks from TransUnion bureau.
Signature verified via HMAC before processing.
"""
from __future__ import annotations
import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException, status, Header
from typing import Optional

from app.core.config import settings
from app.tasks.bureau_tasks import process_bureau_webhook

logger = logging.getLogger(__name__)
router = APIRouter()


def verify_transunion_signature(
    payload_bytes: bytes,
    signature_header: str,
    secret: str,
) -> bool:
    """Verify HMAC-SHA256 signature from TransUnion."""
    expected = hmac.new(
        secret.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


@router.post("/transunion", status_code=status.HTTP_200_OK)
async def transunion_webhook(
    request: Request,
    x_transunion_signature: Optional[str] = Header(None),
):
    """
    Receive async credit bureau callback from TransUnion.
    Verifies signature, enqueues Celery task for processing.
    All responses return 200 to prevent retries on our errors.
    """
    body = await request.body()

    # Verify signature
    if not x_transunion_signature:
        logger.warning("TransUnion webhook received without signature header")
        # Return 200 anyway to avoid TransUnion retrying
        return {"status": "received", "note": "missing_signature"}

    if not verify_transunion_signature(
        body, x_transunion_signature, settings.TRANSUNION_WEBHOOK_SECRET
    ):
        logger.error("TransUnion webhook signature verification FAILED")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature",
        )

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        logger.error("TransUnion webhook — invalid JSON payload")
        return {"status": "error", "note": "invalid_json"}

    event_type = payload.get("event_type", "unknown")
    reference_id = payload.get("reference_id")

    logger.info(
        "TransUnion webhook received: event=%s reference=%s",
        event_type,
        reference_id,
    )

    # Enqueue background processing
    process_bureau_webhook.delay(payload)

    return {
        "status": "accepted",
        "event_type": event_type,
        "reference_id": reference_id,
        "received_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/transunion/health")
async def webhook_health():
    """Health check for webhook receiver — used by TransUnion to verify endpoint."""
    return {"status": "ok", "service": "ramus-webhook-receiver", "version": "1.0.0"}
