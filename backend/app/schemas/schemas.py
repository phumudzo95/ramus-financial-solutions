"""
Pydantic v2 schemas — request/response models for all API endpoints.
"""
from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Any, Dict
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, ConfigDict


# ── Shared ────────────────────────────────────────────────────────────────────

class PaginatedResponse(BaseModel):
    total: int
    page: int
    per_page: int


# ── Auth ──────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=10, max_length=128)
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    role: str


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    email: str
    first_name: str
    last_name: str
    role: str
    is_active: bool
    created_at: datetime


# ── Applications ──────────────────────────────────────────────────────────────

class ApplicationCreate(BaseModel):
    requested_amount: Decimal = Field(..., gt=0, le=500000)
    requested_term_months: int = Field(..., ge=1, le=84)
    loan_purpose: str = Field(..., max_length=100)
    monthly_income: Decimal = Field(..., gt=0)
    monthly_expenses: Decimal = Field(..., ge=0)
    employment_type: str = Field(..., pattern="^(employed|self_employed|contract|pensioner)$")
    employment_duration_months: int = Field(..., ge=0)
    employer_name: Optional[str] = Field(None, max_length=200)


class ApplicationStatusUpdate(BaseModel):
    status: str
    reason: Optional[str] = Field(None, max_length=500)


class ApplicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    reference_number: str
    status: str
    requested_amount: Decimal
    requested_term_months: int
    loan_purpose: str
    employment_type: str
    submitted_at: Optional[datetime]
    created_at: datetime
    assigned_worker_id: Optional[UUID]


class ApplicationListResponse(PaginatedResponse):
    items: List[ApplicationResponse]


# ── Documents ─────────────────────────────────────────────────────────────────

class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    application_id: UUID
    document_type: str
    file_name: str
    file_size_bytes: int
    status: str
    uploaded_at: datetime
    download_url: Optional[str] = None


class DocumentListResponse(PaginatedResponse):
    items: List[DocumentResponse]


# ── Decisions ─────────────────────────────────────────────────────────────────

class DecisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    application_id: UUID
    is_automated: bool
    outcome: str
    risk_category: str
    explanation: str
    rules_applied: List[Dict[str, Any]]
    approved_amount: Optional[Decimal]
    approved_term_months: Optional[int]
    approved_rate_percent: Optional[Decimal]
    is_override: bool
    override_reason: Optional[str]
    created_at: datetime


class DecisionOverrideRequest(BaseModel):
    outcome: str = Field(..., pattern="^(approve|decline)$")
    approved_amount: Optional[Decimal] = Field(None, gt=0)
    approved_term_months: Optional[int] = Field(None, ge=1, le=84)
    approved_rate_percent: Optional[Decimal] = Field(None, gt=0, le=100)
    override_reason: str = Field(..., min_length=20, max_length=1000)


# ── Consent ───────────────────────────────────────────────────────────────────

class ConsentGrantRequest(BaseModel):
    application_id: Optional[UUID] = None
    purpose: str
    consent_text_version: str = "1.0"
    is_granted: bool


class ConsentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    purpose: str
    is_granted: bool
    granted_at: Optional[datetime]
    created_at: datetime


# ── Credit Bureau ─────────────────────────────────────────────────────────────

class BureauCheckRequest(BaseModel):
    application_id: UUID
    consent_id: UUID


class CreditSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    application_id: UUID
    bureau_provider: str
    credit_score: Optional[int]
    risk_category: Optional[str]
    total_accounts: Optional[int]
    negative_listings_count: Optional[int]
    judgements_count: Optional[int]
    total_outstanding_debt: Optional[Decimal]
    monthly_obligations: Optional[Decimal]
    status: str
    requested_at: datetime
    received_at: Optional[datetime]


# ── Workflow ──────────────────────────────────────────────────────────────────

class WorkflowQueueResponse(BaseModel):
    worker_id: UUID
    worker_name: str
    assigned_count: int
    queue_items: List[ApplicationResponse]


class AssignRequest(BaseModel):
    application_id: UUID
    worker_id: UUID


# ── Admin ─────────────────────────────────────────────────────────────────────

class DashboardStats(BaseModel):
    total_applications: int
    pending_review: int
    approved_today: int
    declined_today: int
    avg_processing_hours: float
    total_disbursed_zar: Decimal


class DecisionRuleCreate(BaseModel):
    name: str = Field(..., max_length=100)
    description: str
    rule_type: str
    condition: Dict[str, Any]
    action: str
    priority: int = Field(..., ge=1)
    effective_from: datetime


class DecisionRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    description: str
    rule_type: str
    condition: Dict[str, Any]
    action: str
    priority: int
    is_active: bool
    version: int
    effective_from: datetime
    created_at: datetime


# ── Webhooks ──────────────────────────────────────────────────────────────────

class WebhookPayload(BaseModel):
    event_type: str
    reference_id: str
    data: Dict[str, Any]
    timestamp: datetime
    signature: str
