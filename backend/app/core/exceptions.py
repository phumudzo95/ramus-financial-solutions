"""
Custom exception hierarchy for Ramus Credit System.
All exceptions map cleanly to HTTP responses via main.py exception handlers.
"""
from typing import Optional, Dict, Any
from fastapi import status


class RamusBaseException(Exception):
    """Base exception — all custom exceptions inherit from this."""
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code: str = "INTERNAL_ERROR"

    def __init__(self, message: str, error_code: Optional[str] = None):
        self.message = message
        if error_code:
            self.error_code = error_code
        super().__init__(message)


# ── Auth / Access ─────────────────────────────────────────────────────────────

class AuthenticationException(RamusBaseException):
    status_code = status.HTTP_401_UNAUTHORIZED
    error_code = "AUTHENTICATION_FAILED"


class AuthorizationException(RamusBaseException):
    status_code = status.HTTP_403_FORBIDDEN
    error_code = "FORBIDDEN"


class TokenExpiredException(AuthenticationException):
    error_code = "TOKEN_EXPIRED"


class AccountLockedException(AuthenticationException):
    error_code = "ACCOUNT_LOCKED"


# ── Validation ────────────────────────────────────────────────────────────────

class ValidationException(RamusBaseException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "VALIDATION_ERROR"

    def __init__(self, message: str, fields: Optional[Dict[str, Any]] = None):
        self.fields = fields or {}
        super().__init__(message)


# ── Resource ──────────────────────────────────────────────────────────────────

class NotFoundException(RamusBaseException):
    status_code = status.HTTP_404_NOT_FOUND
    error_code = "NOT_FOUND"


class ConflictException(RamusBaseException):
    status_code = status.HTTP_409_CONFLICT
    error_code = "CONFLICT"


# ── Business Logic ────────────────────────────────────────────────────────────

class ApplicationException(RamusBaseException):
    status_code = status.HTTP_400_BAD_REQUEST
    error_code = "APPLICATION_ERROR"


class ConsentRequiredException(RamusBaseException):
    status_code = status.HTTP_403_FORBIDDEN
    error_code = "CONSENT_REQUIRED"


class DecisionEngineException(RamusBaseException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code = "DECISION_ENGINE_ERROR"


class WorkflowException(RamusBaseException):
    status_code = status.HTTP_400_BAD_REQUEST
    error_code = "WORKFLOW_ERROR"


# ── External Integrations ─────────────────────────────────────────────────────

class BureauException(RamusBaseException):
    status_code = status.HTTP_502_BAD_GATEWAY
    error_code = "BUREAU_ERROR"


class BureauTimeoutException(BureauException):
    error_code = "BUREAU_TIMEOUT"


class BureauRateLimitException(BureauException):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    error_code = "BUREAU_RATE_LIMITED"


class DocumentStorageException(RamusBaseException):
    status_code = status.HTTP_502_BAD_GATEWAY
    error_code = "DOCUMENT_STORAGE_ERROR"


# ── Encryption ────────────────────────────────────────────────────────────────

class EncryptionException(RamusBaseException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code = "ENCRYPTION_ERROR"
