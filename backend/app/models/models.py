"""
Database Models — Complete Schema
All tables use UUIDs as primary keys.
Sensitive fields (ID numbers, income) are encrypted at rest via KMS.
"""
from datetime import datetime
from decimal import Decimal
from enum import Enum as PyEnum
import uuid

from sqlalchemy import (
    Column, String, Boolean, DateTime, Numeric, Integer,
    ForeignKey, Text, JSON, Enum, Index, UniqueConstraint,
    CheckConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship, DeclarativeBase
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


# ── Enums ─────────────────────────────────────────────────────────────────────

class UserRole(str, PyEnum):
    CLIENT = "client"
    WORKER = "worker"
    ADMIN = "admin"


class ApplicationStatus(str, PyEnum):
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    MANUAL_REVIEW = "manual_review"
    APPROVED = "approved"
    DECLINED = "declined"
    COMPLETED = "completed"
    WITHDRAWN = "withdrawn"


class DecisionOutcome(str, PyEnum):
    APPROVE = "approve"
    DECLINE = "decline"
    MANUAL_REVIEW = "manual_review"


class RiskCategory(str, PyEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


class ConsentPurpose(str, PyEnum):
    CREDIT_CHECK = "credit_check"
    IDENTITY_VERIFICATION = "identity_verification"
    AFFORDABILITY_ASSESSMENT = "affordability_assessment"


class BureauProvider(str, PyEnum):
    TRANSUNION = "transunion"
    EXPERIAN = "experian"       # Future
    COMPUSCAN = "compuscan"     # Future (SA)


class NotificationEvent(str, PyEnum):
    APPLICATION_SUBMITTED = "application_submitted"
    STATUS_CHANGED = "status_changed"
    DOCUMENT_REQUESTED = "document_requested"
    APPROVED = "approved"
    DECLINED = "declined"
    MANUAL_REVIEW_ASSIGNED = "manual_review_assigned"
    CREDIT_CHECK_INITIATED = "credit_check_initiated"


class AuditAction(str, PyEnum):
    # User actions
    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"
    USER_CREATED = "user_created"
    USER_UPDATED = "user_updated"
    USER_ROLE_CHANGED = "user_role_changed"
    # Application actions
    APPLICATION_CREATED = "application_created"
    APPLICATION_UPDATED = "application_updated"
    APPLICATION_STATUS_CHANGED = "application_status_changed"
    APPLICATION_ASSIGNED = "application_assigned"
    APPLICATION_ESCALATED = "application_escalated"
    # Decision
    DECISION_MADE = "decision_made"
    DECISION_OVERRIDDEN = "decision_overridden"
    # Document
    DOCUMENT_UPLOADED = "document_uploaded"
    DOCUMENT_REQUESTED = "document_requested"
    DOCUMENT_REVIEWED = "document_reviewed"
    # Credit Bureau
    BUREAU_REQUEST_INITIATED = "bureau_request_initiated"
    BUREAU_RESPONSE_RECEIVED = "bureau_response_received"
    BUREAU_WEBHOOK_RECEIVED = "bureau_webhook_received"
    BUREAU_REQUEST_FAILED = "bureau_request_failed"
    # Consent
    CONSENT_GRANTED = "consent_granted"
    CONSENT_REVOKED = "consent_revoked"
    # Rules
    RULE_CREATED = "rule_created"
    RULE_UPDATED = "rule_updated"
    RULE_DELETED = "rule_deleted"


# ── Base Mixin ────────────────────────────────────────────────────────────────

class TimestampMixin:
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


# ── Users ─────────────────────────────────────────────────────────────────────

class User(Base, TimestampMixin):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), nullable=False, default=UserRole.CLIENT)

    # KMS-encrypted PII
    first_name_enc = Column(Text, nullable=False)         # encrypted
    last_name_enc = Column(Text, nullable=False)          # encrypted
    id_number_enc = Column(Text, nullable=True)           # encrypted SA ID
    phone_enc = Column(Text, nullable=True)               # encrypted

    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    failed_login_attempts = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime(timezone=True), nullable=True)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    mfa_enabled = Column(Boolean, default=False, nullable=False)
    mfa_secret_enc = Column(Text, nullable=True)

    # Relationships
    applications = relationship("Application", back_populates="applicant", foreign_keys="Application.applicant_id")
    assigned_applications = relationship("Application", back_populates="assigned_worker", foreign_keys="Application.assigned_worker_id")
    consents = relationship("Consent", back_populates="user")
    audit_logs = relationship("AuditLog", back_populates="actor", foreign_keys="AuditLog.actor_id")
    refresh_tokens = relationship("RefreshToken", back_populates="user")

    __table_args__ = (
        Index("ix_users_email_role", "email", "role"),
        CheckConstraint("failed_login_attempts >= 0", name="ck_users_failed_logins"),
    )


class RefreshToken(Base, TimestampMixin):
    __tablename__ = "refresh_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash = Column(String(255), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked = Column(Boolean, default=False, nullable=False)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)

    user = relationship("User", back_populates="refresh_tokens")


# ── Applications ──────────────────────────────────────────────────────────────

class Application(Base, TimestampMixin):
    __tablename__ = "applications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reference_number = Column(String(20), unique=True, nullable=False, index=True)
    applicant_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    assigned_worker_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)

    status = Column(Enum(ApplicationStatus), nullable=False, default=ApplicationStatus.SUBMITTED, index=True)

    # Loan details
    requested_amount = Column(Numeric(12, 2), nullable=False)
    requested_term_months = Column(Integer, nullable=False)
    loan_purpose = Column(String(100), nullable=False)

    # Encrypted financial data
    monthly_income_enc = Column(Text, nullable=True)      # encrypted
    monthly_expenses_enc = Column(Text, nullable=True)    # encrypted
    employer_name_enc = Column(Text, nullable=True)       # encrypted

    # Employment
    employment_type = Column(String(50), nullable=True)   # employed/self-employed/contract
    employment_duration_months = Column(Integer, nullable=True)

    # Internal
    internal_notes = Column(Text, nullable=True)
    priority_level = Column(Integer, default=1, nullable=False)  # 1=normal, 2=high, 3=urgent
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    escalated_at = Column(DateTime(timezone=True), nullable=True)
    escalation_reason = Column(Text, nullable=True)

    # Relationships
    applicant = relationship("User", back_populates="applications", foreign_keys=[applicant_id])
    assigned_worker = relationship("User", back_populates="assigned_applications", foreign_keys=[assigned_worker_id])
    documents = relationship("Document", back_populates="application")
    decisions = relationship("Decision", back_populates="application")
    credit_snapshots = relationship("CreditSnapshot", back_populates="application")
    consents = relationship("Consent", back_populates="application")
    workflow_events = relationship("WorkflowEvent", back_populates="application")
    worker_notes = relationship("WorkerNote", back_populates="application")
    document_requests = relationship("DocumentRequest", back_populates="application")

    __table_args__ = (
        CheckConstraint("requested_amount > 0", name="ck_app_positive_amount"),
        CheckConstraint("requested_term_months > 0", name="ck_app_positive_term"),
        CheckConstraint("priority_level BETWEEN 1 AND 3", name="ck_app_priority"),
        Index("ix_applications_status_worker", "status", "assigned_worker_id"),
        Index("ix_applications_applicant_status", "applicant_id", "status"),
    )


class WorkflowEvent(Base):
    """Immutable log of all application state transitions."""
    __tablename__ = "workflow_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id = Column(UUID(as_uuid=True), ForeignKey("applications.id"), nullable=False, index=True)
    actor_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    from_status = Column(Enum(ApplicationStatus), nullable=True)
    to_status = Column(Enum(ApplicationStatus), nullable=False)
    reason = Column(Text, nullable=True)
    metadata = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    application = relationship("Application", back_populates="workflow_events")


class WorkerNote(Base, TimestampMixin):
    __tablename__ = "worker_notes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id = Column(UUID(as_uuid=True), ForeignKey("applications.id"), nullable=False, index=True)
    author_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    note = Column(Text, nullable=False)
    is_internal = Column(Boolean, default=True, nullable=False)

    application = relationship("Application", back_populates="worker_notes")


# ── Documents ─────────────────────────────────────────────────────────────────

class Document(Base, TimestampMixin):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id = Column(UUID(as_uuid=True), ForeignKey("applications.id"), nullable=False, index=True)
    uploader_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    document_type = Column(String(50), nullable=False)   # id_document, payslip, bank_statement, etc.
    file_name = Column(String(255), nullable=False)
    s3_key = Column(String(500), nullable=False)          # S3 object key (encrypted bucket)
    mime_type = Column(String(100), nullable=False)
    file_size_bytes = Column(Integer, nullable=False)
    checksum_sha256 = Column(String(64), nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    verified_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    rejection_reason = Column(Text, nullable=True)

    application = relationship("Application", back_populates="documents")


class DocumentRequest(Base, TimestampMixin):
    __tablename__ = "document_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id = Column(UUID(as_uuid=True), ForeignKey("applications.id"), nullable=False, index=True)
    requested_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    document_type = Column(String(50), nullable=False)
    reason = Column(Text, nullable=False)
    due_date = Column(DateTime(timezone=True), nullable=True)
    is_fulfilled = Column(Boolean, default=False, nullable=False)
    fulfilled_at = Column(DateTime(timezone=True), nullable=True)

    application = relationship("Application", back_populates="document_requests")


# ── Decisions ─────────────────────────────────────────────────────────────────

class Decision(Base):
    """Immutable decision record. Never updated — only new records appended."""
    __tablename__ = "decisions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id = Column(UUID(as_uuid=True), ForeignKey("applications.id"), nullable=False, index=True)
    made_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)  # None = engine
    is_automated = Column(Boolean, nullable=False)
    outcome = Column(Enum(DecisionOutcome), nullable=False)
    risk_category = Column(Enum(RiskCategory), nullable=False)
    explanation = Column(Text, nullable=False)
    rules_applied = Column(JSONB, nullable=False)          # snapshot of rules at decision time
    credit_snapshot_id = Column(UUID(as_uuid=True), ForeignKey("credit_snapshots.id"), nullable=True)
    approved_amount = Column(Numeric(12, 2), nullable=True)
    approved_term_months = Column(Integer, nullable=True)
    approved_rate_percent = Column(Numeric(5, 2), nullable=True)
    is_override = Column(Boolean, default=False, nullable=False)
    override_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    application = relationship("Application", back_populates="decisions")
    credit_snapshot = relationship("CreditSnapshot")


# ── Credit Bureau ─────────────────────────────────────────────────────────────

class CreditSnapshot(Base):
    """Normalized credit data — immutable record of bureau response."""
    __tablename__ = "credit_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id = Column(UUID(as_uuid=True), ForeignKey("applications.id"), nullable=False, index=True)
    consent_id = Column(UUID(as_uuid=True), ForeignKey("consents.id"), nullable=False)
    bureau_provider = Column(Enum(BureauProvider), nullable=False)
    bureau_request_id = Column(String(255), nullable=True)    # Bureau's reference ID

    # Normalized credit data
    credit_score = Column(Integer, nullable=True)             # 0–999 normalized
    risk_category = Column(Enum(RiskCategory), nullable=True)
    total_accounts = Column(Integer, nullable=True)
    open_accounts = Column(Integer, nullable=True)
    closed_accounts = Column(Integer, nullable=True)
    negative_listings_count = Column(Integer, nullable=True)
    judgements_count = Column(Integer, nullable=True)
    defaults_count = Column(Integer, nullable=True)
    total_outstanding_debt = Column(Numeric(12, 2), nullable=True)
    monthly_obligations = Column(Numeric(12, 2), nullable=True)
    oldest_account_months = Column(Integer, nullable=True)
    enquiries_last_90_days = Column(Integer, nullable=True)

    # Encrypted raw response (stored for audit, never used for logic)
    raw_response_enc = Column(Text, nullable=True)

    # Status
    status = Column(String(20), nullable=False, default="pending")  # pending/success/failed/timeout
    error_code = Column(String(50), nullable=True)
    error_message = Column(Text, nullable=True)
    requested_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    received_at = Column(DateTime(timezone=True), nullable=True)

    application = relationship("Application", back_populates="credit_snapshots")
    consent = relationship("Consent")


class BureauApiLog(Base):
    """Complete log of all external credit bureau API calls — immutable."""
    __tablename__ = "bureau_api_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    credit_snapshot_id = Column(UUID(as_uuid=True), ForeignKey("credit_snapshots.id"), nullable=True, index=True)
    bureau_provider = Column(Enum(BureauProvider), nullable=False)
    endpoint = Column(String(255), nullable=False)
    http_method = Column(String(10), nullable=False)
    request_headers_enc = Column(Text, nullable=False)       # encrypted (contains auth)
    request_body_enc = Column(Text, nullable=False)          # encrypted (contains PII)
    response_status_code = Column(Integer, nullable=True)
    response_body_enc = Column(Text, nullable=True)          # encrypted
    duration_ms = Column(Integer, nullable=True)
    attempt_number = Column(Integer, default=1, nullable=False)
    is_webhook = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_bureau_api_logs_provider_date", "bureau_provider", "created_at"),
    )


# ── Consent ───────────────────────────────────────────────────────────────────

class Consent(Base):
    """
    Explicit recorded consent before any credit bureau request.
    Immutable — consent records are never updated or deleted.
    """
    __tablename__ = "consents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    application_id = Column(UUID(as_uuid=True), ForeignKey("applications.id"), nullable=True, index=True)
    purpose = Column(Enum(ConsentPurpose), nullable=False)
    consent_text = Column(Text, nullable=False)              # exact text presented to user
    consent_text_version = Column(String(20), nullable=False)
    is_granted = Column(Boolean, nullable=False)
    granted_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    revocation_reason = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=False)
    user_agent = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="consents")
    application = relationship("Application", back_populates="consents")


# ── Audit Logs ────────────────────────────────────────────────────────────────

class AuditLog(Base):
    """
    Immutable, append-only audit trail for all system actions.
    Never updated or deleted. Archived to S3 after retention period.
    """
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    action = Column(Enum(AuditAction), nullable=False, index=True)
    actor_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    actor_role = Column(Enum(UserRole), nullable=True)
    actor_ip = Column(String(45), nullable=True)
    target_type = Column(String(50), nullable=True)          # "application", "user", "document", etc.
    target_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    before_state = Column(JSONB, nullable=True)
    after_state = Column(JSONB, nullable=True)
    metadata = Column(JSONB, nullable=True)
    request_id = Column(String(36), nullable=True, index=True)
    session_id = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    actor = relationship("User", back_populates="audit_logs", foreign_keys=[actor_id])

    __table_args__ = (
        Index("ix_audit_logs_created_action", "created_at", "action"),
        Index("ix_audit_logs_target", "target_type", "target_id"),
    )


# ── Decision Rules ────────────────────────────────────────────────────────────

class DecisionRule(Base, TimestampMixin):
    """
    Admin-configurable rules for the decision engine.
    Rules are versioned — old versions kept for audit trail.
    """
    __tablename__ = "decision_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=False)
    rule_type = Column(String(50), nullable=False)           # score_threshold, dti, income, negative_listings, etc.
    condition = Column(JSONB, nullable=False)                 # {"field": "credit_score", "operator": ">=", "value": 700}
    action = Column(Enum(DecisionOutcome), nullable=False)
    priority = Column(Integer, nullable=False)               # Lower = evaluated first
    is_active = Column(Boolean, default=True, nullable=False)
    version = Column(Integer, default=1, nullable=False)
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    effective_from = Column(DateTime(timezone=True), nullable=False)
    effective_until = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_decision_rules_active_priority", "is_active", "priority"),
    )


# ── Notifications ─────────────────────────────────────────────────────────────

class NotificationLog(Base, TimestampMixin):
    """Log of all email notifications sent."""
    __tablename__ = "notification_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recipient_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    recipient_email = Column(String(255), nullable=False)
    event = Column(Enum(NotificationEvent), nullable=False)
    application_id = Column(UUID(as_uuid=True), ForeignKey("applications.id"), nullable=True)
    subject = Column(String(255), nullable=False)
    template_name = Column(String(100), nullable=False)
    ses_message_id = Column(String(255), nullable=True)
    status = Column(String(20), nullable=False, default="sent")   # sent/failed/bounced
    error_message = Column(Text, nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
