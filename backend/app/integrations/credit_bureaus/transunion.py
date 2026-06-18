"""
Credit Bureau Integration Layer — TransUnion (Primary)
Pluggable architecture: add new bureaus by implementing BureauProvider protocol.

IMPORTANT: This is the ONLY place external bureau APIs are called.
Business logic must NEVER call bureau APIs directly.
All calls are logged in bureau_api_logs (immutable, encrypted).
"""
from __future__ import annotations
import asyncio
import hashlib
import json
import logging
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.encryption import EncryptionService
from app.models.models import BureauApiLog, BureauProvider, CreditSnapshot, RiskCategory

logger = logging.getLogger(__name__)


# ── Normalized Credit Data Model ──────────────────────────────────────────────

@dataclass
class NormalizedCreditData:
    """
    Unified internal credit model — provider-agnostic.
    All bureaus normalize into this model before any business logic runs.
    """
    bureau_provider: str
    bureau_request_id: str

    # Score
    credit_score: Optional[int]                    # 0–999
    risk_category: Optional[str]                   # low/medium/high/very_high

    # Account summary
    total_accounts: int = 0
    open_accounts: int = 0
    closed_accounts: int = 0
    oldest_account_months: int = 0

    # Negatives
    negative_listings_count: int = 0
    judgements_count: int = 0
    defaults_count: int = 0
    adverse_count: int = 0

    # Affordability
    total_outstanding_debt: Decimal = Decimal("0")
    monthly_obligations: Decimal = Decimal("0")
    enquiries_last_90_days: int = 0

    # Metadata
    retrieved_at: Optional[datetime] = None
    is_frozen: bool = False


# ── Bureau Provider Protocol ──────────────────────────────────────────────────

class BureauProviderBase(ABC):
    """
    Abstract base class for credit bureau providers.
    Implement this to add a new bureau — no changes to business logic required.
    """

    @abstractmethod
    async def fetch_credit_report(
        self,
        id_number: str,
        first_name: str,
        last_name: str,
        consent_id: str,
    ) -> NormalizedCreditData:
        pass

    @abstractmethod
    async def health_check(self) -> dict:
        pass

    @abstractmethod
    def normalize_response(self, raw: dict) -> NormalizedCreditData:
        pass


# ── TransUnion Provider ───────────────────────────────────────────────────────

class TransUnionProvider(BureauProviderBase):
    """
    TransUnion South Africa integration.
    Uses OAuth2 client credentials for auth (token cached in memory).
    All requests and responses are logged encrypted.
    """

    def __init__(self, db: AsyncSession, encryption: EncryptionService):
        self.db = db
        self.encryption = encryption
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0
        self.base_url = settings.TRANSUNION_API_BASE_URL
        self.client_id = settings.TRANSUNION_CLIENT_ID
        self.client_secret = settings.TRANSUNION_CLIENT_SECRET
        self.api_key = settings.TRANSUNION_API_KEY
        self.max_retries = settings.TRANSUNION_MAX_RETRIES
        self.timeout = settings.TRANSUNION_TIMEOUT_SECONDS

    # ── Auth ─────────────────────────────────────────────────────────────────

    async def _get_access_token(self) -> str:
        """Get or refresh OAuth2 access token."""
        now = time.time()
        if self._access_token and now < self._token_expires_at - 60:
            return self._access_token

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.base_url}/oauth/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
                headers={"X-API-Key": self.api_key},
            )
            resp.raise_for_status()
            token_data = resp.json()
            self._access_token = token_data["access_token"]
            self._token_expires_at = now + token_data.get("expires_in", 3600)
            return self._access_token

    # ── Credit Report Fetch ───────────────────────────────────────────────────

    async def fetch_credit_report(
        self,
        id_number: str,
        first_name: str,
        last_name: str,
        consent_id: str,
    ) -> NormalizedCreditData:
        """
        Fetch credit report from TransUnion with retry and full logging.
        Raises BureauIntegrationError on persistent failure.
        """
        endpoint = f"{self.base_url}/consumer/credit-report"
        request_body = {
            "idNumber": id_number,
            "firstName": first_name,
            "lastName": last_name,
            "consentReference": consent_id,
            "reportType": "FULL",
            "requestId": str(uuid.uuid4()),
        }

        last_error = None
        for attempt in range(1, self.max_retries + 1):
            start_ms = int(time.time() * 1000)
            token = await self._get_access_token()
            headers = {
                "Authorization": f"Bearer {token}",
                "X-API-Key": self.api_key,
                "Content-Type": "application/json",
                "X-Consent-Reference": consent_id,
            }

            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        endpoint,
                        json=request_body,
                        headers=headers,
                    )
                    duration_ms = int(time.time() * 1000) - start_ms

                    await self._log_api_call(
                        endpoint=endpoint,
                        method="POST",
                        request_headers=headers,
                        request_body=request_body,
                        response_status=response.status_code,
                        response_body=response.text,
                        duration_ms=duration_ms,
                        attempt=attempt,
                    )

                    if response.status_code == 200:
                        raw = response.json()
                        return self.normalize_response(raw)

                    if response.status_code in (429, 503):
                        # Rate limited or unavailable — exponential backoff
                        wait = 2 ** attempt
                        logger.warning(
                            "TransUnion %s on attempt %d — retrying in %ds",
                            response.status_code, attempt, wait,
                        )
                        await asyncio.sleep(wait)
                        last_error = BureauIntegrationError(
                            f"TransUnion returned {response.status_code}",
                            provider="transunion",
                            status_code=response.status_code,
                        )
                        continue

                    # Non-retryable error
                    raise BureauIntegrationError(
                        f"TransUnion error {response.status_code}: {response.text}",
                        provider="transunion",
                        status_code=response.status_code,
                    )

            except httpx.TimeoutException as e:
                duration_ms = int(time.time() * 1000) - start_ms
                await self._log_api_call(
                    endpoint=endpoint,
                    method="POST",
                    request_headers=headers,
                    request_body=request_body,
                    response_status=None,
                    response_body=None,
                    duration_ms=duration_ms,
                    attempt=attempt,
                    error=str(e),
                )
                last_error = BureauIntegrationError(
                    f"TransUnion timeout on attempt {attempt}",
                    provider="transunion",
                )
                await asyncio.sleep(2 ** attempt)
                continue

        raise last_error or BureauIntegrationError(
            "TransUnion: all retries exhausted", provider="transunion"
        )

    # ── Normalization ─────────────────────────────────────────────────────────

    def normalize_response(self, raw: dict) -> NormalizedCreditData:
        """
        Normalize TransUnion response into the unified NormalizedCreditData model.
        This method is the ONLY place TransUnion-specific field names appear.
        """
        try:
            consumer = raw.get("consumer", {})
            score_info = raw.get("scoreInfo", {})
            accounts = raw.get("accounts", {})
            public_records = raw.get("publicRecords", {})
            affordability = raw.get("affordabilityIndicators", {})
            enquiries = raw.get("enquiries", {})

            # Score normalization (TransUnion uses 0-999 scale)
            raw_score = score_info.get("score")
            credit_score = int(raw_score) if raw_score is not None else None

            # Risk category from TransUnion risk band
            risk_band = score_info.get("riskBand", "").upper()
            risk_map = {
                "VERY_LOW": "low",
                "LOW": "low",
                "MODERATE": "medium",
                "HIGH": "high",
                "VERY_HIGH": "very_high",
            }
            risk_category = risk_map.get(risk_band, "high")

            return NormalizedCreditData(
                bureau_provider="transunion",
                bureau_request_id=raw.get("requestId", str(uuid.uuid4())),
                credit_score=credit_score,
                risk_category=risk_category,
                total_accounts=accounts.get("totalAccounts", 0),
                open_accounts=accounts.get("openAccounts", 0),
                closed_accounts=accounts.get("closedAccounts", 0),
                oldest_account_months=accounts.get("oldestAccountAgeMonths", 0),
                negative_listings_count=public_records.get("totalAdverseListings", 0),
                judgements_count=public_records.get("judgements", 0),
                defaults_count=public_records.get("defaults", 0),
                adverse_count=public_records.get("adverseListings", 0),
                total_outstanding_debt=Decimal(str(affordability.get("totalOutstandingBalance", 0))),
                monthly_obligations=Decimal(str(affordability.get("totalMonthlyInstalment", 0))),
                enquiries_last_90_days=enquiries.get("last90Days", 0),
                retrieved_at=datetime.now(timezone.utc),
                is_frozen=consumer.get("isFrozen", False),
            )
        except (KeyError, ValueError, TypeError) as e:
            logger.error("TransUnion normalization failed: %s | raw keys: %s", e, list(raw.keys()))
            raise BureauIntegrationError(f"Response normalization failed: {e}", provider="transunion")

    # ── Webhook Handler ───────────────────────────────────────────────────────

    async def handle_webhook(self, payload: dict, signature: str) -> dict:
        """
        Verify and process TransUnion webhook notifications.
        TransUnion sends async updates for: report_ready, consent_expiry.
        """
        if not self._verify_webhook_signature(payload, signature):
            raise BureauIntegrationError(
                "Invalid webhook signature", provider="transunion"
            )

        event_type = payload.get("eventType")
        logger.info("TransUnion webhook received: %s", event_type)

        await self._log_api_call(
            endpoint="/webhooks/transunion",
            method="WEBHOOK",
            request_headers={},
            request_body=payload,
            response_status=200,
            response_body=None,
            duration_ms=0,
            is_webhook=True,
        )

        return {"event_type": event_type, "processed": True}

    def _verify_webhook_signature(self, payload: dict, signature: str) -> bool:
        """HMAC-SHA256 signature verification for TransUnion webhooks."""
        import hmac
        secret = settings.TRANSUNION_WEBHOOK_SECRET.encode()
        computed = hmac.new(
            secret,
            json.dumps(payload, separators=(",", ":")).encode(),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(f"sha256={computed}", signature)

    # ── Health Check ──────────────────────────────────────────────────────────

    async def health_check(self) -> dict:
        try:
            token = await self._get_access_token()
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{self.base_url}/health",
                    headers={"Authorization": f"Bearer {token}"},
                )
                return {
                    "provider": "transunion",
                    "status": "healthy" if resp.status_code == 200 else "degraded",
                    "status_code": resp.status_code,
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                }
        except Exception as e:
            return {
                "provider": "transunion",
                "status": "unhealthy",
                "error": str(e),
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }

    # ── Logging ───────────────────────────────────────────────────────────────

    async def _log_api_call(
        self,
        endpoint: str,
        method: str,
        request_headers: dict,
        request_body: dict,
        response_status: Optional[int],
        response_body: Optional[str],
        duration_ms: int,
        attempt: int = 1,
        error: Optional[str] = None,
        is_webhook: bool = False,
        credit_snapshot_id: Optional[str] = None,
    ):
        """Encrypt and persist every API call — immutable audit record."""
        try:
            log = BureauApiLog(
                credit_snapshot_id=credit_snapshot_id,
                bureau_provider=BureauProvider.TRANSUNION,
                endpoint=endpoint,
                http_method=method,
                request_headers_enc=self.encryption.encrypt(json.dumps(request_headers)),
                request_body_enc=self.encryption.encrypt(json.dumps(request_body)),
                response_status_code=response_status,
                response_body_enc=self.encryption.encrypt(response_body or error or ""),
                duration_ms=duration_ms,
                attempt_number=attempt,
                is_webhook=is_webhook,
            )
            self.db.add(log)
            await self.db.flush()
        except Exception as e:
            # Logging must never crash the main flow
            logger.error("Failed to persist bureau API log: %s", e)


# ── Bureau Registry ───────────────────────────────────────────────────────────

class BureauRegistry:
    """
    Central registry for all bureau providers.
    Add a new bureau here — zero changes to business logic.
    """

    def __init__(self, db: AsyncSession, encryption: EncryptionService):
        self._providers: dict[str, BureauProviderBase] = {
            "transunion": TransUnionProvider(db, encryption),
            # "experian": ExperianProvider(db, encryption),      # Future
            # "compuscan": CompuScanProvider(db, encryption),    # Future
        }

    def get(self, provider: str) -> BureauProviderBase:
        p = self._providers.get(provider)
        if not p:
            raise ValueError(f"Unknown bureau provider: {provider}")
        return p

    @property
    def primary(self) -> BureauProviderBase:
        return self._providers["transunion"]

    async def check_all_health(self) -> list[dict]:
        results = []
        for provider in self._providers.values():
            results.append(await provider.health_check())
        return results


# ── Exceptions ────────────────────────────────────────────────────────────────

class BureauIntegrationError(Exception):
    def __init__(self, message: str, provider: str = "", status_code: Optional[int] = None):
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code


# ── Integration Health Endpoint ───────────────────────────────────────────────

async def check_bureau_health() -> dict:
    """Called by /api/v1/health/integrations — no DB needed for basic ping."""
    # Lightweight check using a short-lived client
    results = {}
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                f"{settings.TRANSUNION_API_BASE_URL}/health",
                headers={"X-API-Key": settings.TRANSUNION_API_KEY},
            )
            results["transunion"] = {
                "status": "healthy" if resp.status_code < 300 else "degraded",
                "latency_ms": int(resp.elapsed.total_seconds() * 1000),
            }
    except Exception as e:
        results["transunion"] = {"status": "unhealthy", "error": str(e)}

    return {
        "integrations": results,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
