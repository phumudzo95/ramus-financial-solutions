"""
Core configuration — environment-aware settings for dev / staging / production.
All secrets are loaded from environment variables (AWS SSM / Secrets Manager in prod).
"""
from decimal import Decimal
from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import AnyHttpUrl, field_validator
import json


class Settings(BaseSettings):
    # ── Application ───────────────────────────────────────────────────────────
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    SECRET_KEY: str
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Ramus Financial Solutions Credit System"

    # ── Company / Compliance ─────────────────────────────────────────────────
    COMPANY_NAME: str = "Ramus Financial Solutions"
    NCR_REGISTRATION_NUMBER: str = "NCRCP19178"
    COMPANY_ADDRESS: str = "17 Robert Bruce Road, Beverley Hills Estate, Sandton, 2191"

    # ── Loan Product Rules ───────────────────────────────────────────────────
    # Single short-term loan product: fixed cost of credit, capped amount,
    # repaid in full after 30 days OR over 1–6 months.
    LOAN_MAX_AMOUNT: Decimal = Decimal("5000.00")
    LOAN_MIN_AMOUNT: Decimal = Decimal("500.00")
    LOAN_COST_OF_CREDIT_PERCENT: Decimal = Decimal("30.00")  # total cost, not per annum
    LOAN_TERM_SINGLE_PAYMENT_DAYS: int = 30
    LOAN_TERM_MIN_MONTHS: int = 1
    LOAN_TERM_MAX_MONTHS: int = 6

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20
    DATABASE_POOL_TIMEOUT: int = 30

    # ── Redis (caching, rate-limiting, session store) ─────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_TTL_SECONDS: int = 3600

    # ── Auth / JWT ────────────────────────────────────────────────────────────
    JWT_ALGORITHM: str = "RS256"
    JWT_PRIVATE_KEY: str          # RSA private key PEM
    JWT_PUBLIC_KEY: str           # RSA public key PEM
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── CORS / Hosts ──────────────────────────────────────────────────────────
    ALLOWED_ORIGINS: List[str] = []
    ALLOWED_HOSTS: List[str] = ["*"]

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_origins(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v

    # ── Email (AWS SES) ───────────────────────────────────────────────────────
    EMAIL_ENABLED: bool = True
    EMAIL_FROM_ADDRESS: str = "noreply@ramuscashloans.co.za"
    EMAIL_FROM_NAME: str = "Ramus Financial Solutions"
    AWS_SES_REGION: str = "af-south-1"
    AWS_SES_CONFIGURATION_SET: Optional[str] = None

    # ── AWS ───────────────────────────────────────────────────────────────────
    AWS_REGION: str = "af-south-1"
    AWS_S3_BUCKET_DOCUMENTS: str
    AWS_S3_BUCKET_AUDIT_LOGS: str
    AWS_KMS_KEY_ID: str           # Used for field-level encryption

    # ── Credit Bureau: TransUnion ────────────────────────────────────────────
    TRANSUNION_API_BASE_URL: str = "https://api.transunion.co.za/v1"
    TRANSUNION_API_KEY: str
    TRANSUNION_CLIENT_ID: str
    TRANSUNION_CLIENT_SECRET: str
    TRANSUNION_WEBHOOK_SECRET: str
    TRANSUNION_TIMEOUT_SECONDS: int = 30
    TRANSUNION_MAX_RETRIES: int = 3

    # ── Decision Engine ───────────────────────────────────────────────────────
    DECISION_ENGINE_AUTO_APPROVE_SCORE: int = 700
    DECISION_ENGINE_AUTO_DECLINE_SCORE: int = 450
    DECISION_ENGINE_MAX_DTI_RATIO: float = 0.45   # 45% debt-to-income
    DECISION_ENGINE_MIN_INCOME: float = 3500.0     # ZAR monthly

    # ── Workflow ──────────────────────────────────────────────────────────────
    WORKFLOW_AUTO_ASSIGN: bool = True
    WORKFLOW_ESCALATION_HOURS: int = 24
    WORKFLOW_MAX_WORKER_QUEUE: int = 50

    # ── Rate Limiting ─────────────────────────────────────────────────────────
    RATE_LIMIT_AUTH_PER_MINUTE: int = 10
    RATE_LIMIT_API_PER_MINUTE: int = 120
    RATE_LIMIT_BUREAU_PER_HOUR: int = 100

    # ── Audit ─────────────────────────────────────────────────────────────────
    AUDIT_LOG_RETENTION_DAYS: int = 2555   # 7 years for compliance
    AUDIT_S3_ARCHIVE_AFTER_DAYS: int = 90

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


settings = Settings()
