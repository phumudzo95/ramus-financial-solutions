"""
Integration health checks — used by /api/v1/health/integrations
"""
from __future__ import annotations
import logging
import asyncio
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


async def check_bureau_health() -> dict:
    """Ping all external integrations and return status."""
    results = {}

    # TransUnion ping
    try:
        from app.integrations.credit_bureaus.transunion import TransUnionClient
        client = TransUnionClient()
        ok = await client.ping()
        results["transunion"] = {"status": "ok" if ok else "degraded"}
    except Exception as e:
        results["transunion"] = {"status": "error", "detail": str(e)}

    # S3
    try:
        import boto3
        from app.core.config import settings
        s3 = boto3.client("s3", region_name=settings.AWS_REGION)
        s3.head_bucket(Bucket=settings.AWS_S3_BUCKET_DOCUMENTS)
        results["s3_documents"] = {"status": "ok"}
    except Exception as e:
        results["s3_documents"] = {"status": "error", "detail": str(e)}

    # SES
    try:
        import boto3
        from app.core.config import settings
        ses = boto3.client("ses", region_name=settings.AWS_SES_REGION)
        ses.get_send_quota()
        results["ses_email"] = {"status": "ok"}
    except Exception as e:
        results["ses_email"] = {"status": "error", "detail": str(e)}

    overall = "ok" if all(v["status"] == "ok" for v in results.values()) else "degraded"

    return {
        "overall": overall,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "integrations": results,
    }
