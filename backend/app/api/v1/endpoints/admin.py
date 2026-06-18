"""
Admin/Compliance Endpoint — Admin-only access.
System-wide monitoring, audit logs, decision logs, bureau logs,
user management, role management, decision rule configuration.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.core.security import require_roles
from app.db.session import get_db
from app.models.models import (
    Application, ApplicationStatus, AuditLog, AuditAction,
    BureauApiLog, Decision, DecisionRule, DecisionOutcome,
    NotificationLog, User, UserRole,
)
from app.audit.audit_service import AuditService

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class RuleCreate(BaseModel):
    name: str = Field(..., max_length=100)
    description: str
    rule_type: str
    condition: dict = Field(..., description='e.g. {"field":"credit_score","operator":">=","value":700}')
    action: DecisionOutcome
    priority: int = Field(..., ge=1, le=999)
    effective_from: datetime
    effective_until: Optional[datetime] = None


class RuleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    condition: Optional[dict] = None
    action: Optional[DecisionOutcome] = None
    priority: Optional[int] = None
    is_active: Optional[bool] = None
    effective_until: Optional[datetime] = None


class UserRoleUpdate(BaseModel):
    role: UserRole


class UserStatusUpdate(BaseModel):
    is_active: bool


# ── System Dashboard ──────────────────────────────────────────────────────────

@router.get("/dashboard")
async def get_dashboard(
    current_user: User = Depends(require_roles([UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db),
):
    """System-wide monitoring dashboard for admins."""
    # Application counts by status
    app_counts_result = await db.execute(
        select(Application.status, func.count(Application.id).label("count"))
        .group_by(Application.status)
    )
    app_counts = {row.status.value: row.count for row in app_counts_result.all()}

    # Total users by role
    user_counts_result = await db.execute(
        select(User.role, func.count(User.id).label("count"))
        .group_by(User.role)
    )
    user_counts = {row.role.value: row.count for row in user_counts_result.all()}

    # Decision breakdown
    decision_result = await db.execute(
        select(Decision.outcome, func.count(Decision.id).label("count"))
        .group_by(Decision.outcome)
    )
    decision_counts = {row.outcome.value: row.count for row in decision_result.all()}

    # Bureau API call counts today
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    bureau_today_result = await db.execute(
        select(func.count(BureauApiLog.id))
        .where(BureauApiLog.created_at >= today_start)
    )
    bureau_calls_today = bureau_today_result.scalar_one()

    # Audit activity summary
    audit = AuditService(db)
    audit_summary = await audit.get_audit_summary()

    # Active decision rules
    rules_result = await db.execute(
        select(func.count(DecisionRule.id)).where(DecisionRule.is_active == True)
    )
    active_rules = rules_result.scalar_one()

    return {
        "applications": app_counts,
        "users": user_counts,
        "decisions": decision_counts,
        "bureau_calls_today": bureau_calls_today,
        "active_decision_rules": active_rules,
        "audit_summary": audit_summary,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Audit Logs ────────────────────────────────────────────────────────────────

@router.get("/audit-logs")
async def get_audit_logs(
    action: Optional[AuditAction] = Query(None),
    actor_id: Optional[str] = Query(None),
    target_type: Optional[str] = Query(None),
    from_dt: Optional[datetime] = Query(None),
    to_dt: Optional[datetime] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    current_user: User = Depends(require_roles([UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db),
):
    """Full audit log access for compliance officers."""
    query = select(AuditLog)
    filters = []

    if action:
        filters.append(AuditLog.action == action)
    if actor_id:
        filters.append(AuditLog.actor_id == uuid.UUID(actor_id))
    if target_type:
        filters.append(AuditLog.target_type == target_type)
    if from_dt:
        filters.append(AuditLog.created_at >= from_dt)
    if to_dt:
        filters.append(AuditLog.created_at <= to_dt)

    if filters:
        query = query.where(and_(*filters))

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar_one()

    query = query.order_by(AuditLog.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    logs = result.scalars().all()

    return {
        "items": [
            {
                "id": str(log.id),
                "action": log.action.value,
                "actor_id": str(log.actor_id) if log.actor_id else None,
                "actor_role": log.actor_role.value if log.actor_role else None,
                "actor_ip": log.actor_ip,
                "target_type": log.target_type,
                "target_id": str(log.target_id) if log.target_id else None,
                "before_state": log.before_state,
                "after_state": log.after_state,
                "metadata": log.log_metadata,
                "request_id": log.request_id,
                "created_at": log.created_at.isoformat(),
            }
            for log in logs
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.get("/audit-logs/decisions")
async def get_decision_audit_logs(
    from_dt: Optional[datetime] = Query(None),
    current_user: User = Depends(require_roles([UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db),
):
    """Dedicated decision audit log view."""
    audit = AuditService(db)
    logs = await audit.get_decision_logs(from_dt=from_dt)
    return {"items": [{"id": str(l.id), "action": l.action.value, "metadata": l.log_metadata,
                       "created_at": l.created_at.isoformat()} for l in logs]}


@router.get("/audit-logs/bureau")
async def get_bureau_audit_logs(
    from_dt: Optional[datetime] = Query(None),
    current_user: User = Depends(require_roles([UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db),
):
    """Credit bureau request/response audit logs."""
    audit = AuditService(db)
    logs = await audit.get_bureau_request_logs(from_dt=from_dt)
    return {"items": [{"id": str(l.id), "action": l.action.value, "metadata": l.log_metadata,
                       "created_at": l.created_at.isoformat()} for l in logs]}


# ── Decision Rules Management ─────────────────────────────────────────────────

@router.get("/rules")
async def list_rules(
    is_active: Optional[bool] = Query(None),
    current_user: User = Depends(require_roles([UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db),
):
    """List all decision rules (configurable without code changes)."""
    query = select(DecisionRule)
    if is_active is not None:
        query = query.where(DecisionRule.is_active == is_active)
    result = await db.execute(query.order_by(DecisionRule.priority.asc()))
    rules = result.scalars().all()
    return {"items": [_rule_to_dict(r) for r in rules]}


@router.post("/rules", status_code=status.HTTP_201_CREATED)
async def create_rule(
    payload: RuleCreate,
    current_user: User = Depends(require_roles([UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db),
):
    """Create a new decision rule. Takes effect immediately."""
    audit = AuditService(db)
    rule = DecisionRule(
        name=payload.name,
        description=payload.description,
        rule_type=payload.rule_type,
        condition=payload.condition,
        action=payload.action,
        priority=payload.priority,
        is_active=True,
        version=1,
        created_by_id=current_user.id,
        effective_from=payload.effective_from,
        effective_until=payload.effective_until,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)

    await audit.log(
        action=AuditAction.RULE_CREATED,
        actor_id=str(current_user.id),
        actor_role=current_user.role,
        target_type="decision_rule",
        target_id=str(rule.id),
        after_state=_rule_to_dict(rule),
    )
    return _rule_to_dict(rule)


@router.patch("/rules/{rule_id}")
async def update_rule(
    rule_id: str,
    payload: RuleUpdate,
    current_user: User = Depends(require_roles([UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db),
):
    """Update a decision rule. Changes are versioned in audit log."""
    audit = AuditService(db)
    result = await db.execute(select(DecisionRule).where(DecisionRule.id == uuid.UUID(rule_id)))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    before = _rule_to_dict(rule)

    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(rule, field, value)
    rule.version += 1

    await db.commit()
    await db.refresh(rule)

    await audit.log(
        action=AuditAction.RULE_UPDATED,
        actor_id=str(current_user.id),
        actor_role=current_user.role,
        target_type="decision_rule",
        target_id=str(rule.id),
        before_state=before,
        after_state=_rule_to_dict(rule),
    )
    return _rule_to_dict(rule)


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_rule(
    rule_id: str,
    current_user: User = Depends(require_roles([UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db),
):
    """Deactivate a rule (soft delete — never hard deleted for audit trail)."""
    audit = AuditService(db)
    result = await db.execute(select(DecisionRule).where(DecisionRule.id == uuid.UUID(rule_id)))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    rule.is_active = False
    rule.version += 1
    await db.commit()

    await audit.log(
        action=AuditAction.RULE_DELETED,
        actor_id=str(current_user.id),
        actor_role=current_user.role,
        target_type="decision_rule",
        target_id=str(rule.id),
    )


# ── User Management ───────────────────────────────────────────────────────────

@router.get("/users")
async def list_users(
    role: Optional[UserRole] = Query(None),
    is_active: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    current_user: User = Depends(require_roles([UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db),
):
    query = select(User)
    if role:
        query = query.where(User.role == role)
    if is_active is not None:
        query = query.where(User.is_active == is_active)

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar_one()

    result = await db.execute(
        query.order_by(User.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    )
    users = result.scalars().all()
    return {
        "items": [_user_to_dict(u) for u in users],
        "total": total, "page": page, "per_page": per_page,
    }


@router.patch("/users/{user_id}/role", status_code=status.HTTP_200_OK)
async def update_user_role(
    user_id: str,
    payload: UserRoleUpdate,
    current_user: User = Depends(require_roles([UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db),
):
    audit = AuditService(db)
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    old_role = user.role
    user.role = payload.role
    await db.commit()

    await audit.log(
        action=AuditAction.USER_ROLE_CHANGED,
        actor_id=str(current_user.id),
        actor_role=current_user.role,
        target_type="user",
        target_id=str(user.id),
        before_state={"role": old_role.value},
        after_state={"role": payload.role.value},
    )
    return {"id": user_id, "new_role": payload.role.value}


@router.patch("/users/{user_id}/status")
async def update_user_status(
    user_id: str,
    payload: UserStatusUpdate,
    current_user: User = Depends(require_roles([UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_active = payload.is_active
    await db.commit()
    return {"id": user_id, "is_active": payload.is_active}


# ── Integration Health ─────────────────────────────────────────────────────────

@router.get("/integrations/health")
async def integration_health_detailed(
    current_user: User = Depends(require_roles([UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db),
):
    """Detailed integration health including bureau API stats."""
    from app.integrations.credit_bureaus.transunion import BureauRegistry
    from app.core.encryption import EncryptionService

    enc = EncryptionService()
    registry = BureauRegistry(db, enc)
    bureau_health = await registry.check_all_health()

    # Bureau API stats last 24h
    from datetime import timedelta
    last_24h = datetime.now(timezone.utc) - timedelta(hours=24)
    bureau_stats_result = await db.execute(
        select(
            BureauApiLog.bureau_provider,
            func.count(BureauApiLog.id).label("total"),
            func.avg(BureauApiLog.duration_ms).label("avg_ms"),
            func.sum(
                func.cast(
                    and_(BureauApiLog.response_status_code.isnot(None),
                         BureauApiLog.response_status_code >= 400),
                    db.bind.dialect.type_descriptor(type(1))
                )
            ).label("errors"),
        )
        .where(BureauApiLog.created_at >= last_24h)
        .group_by(BureauApiLog.bureau_provider)
    )

    return {
        "bureau_health": bureau_health,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _rule_to_dict(rule: DecisionRule) -> dict:
    return {
        "id": str(rule.id),
        "name": rule.name,
        "description": rule.description,
        "rule_type": rule.rule_type,
        "condition": rule.condition,
        "action": rule.action.value,
        "priority": rule.priority,
        "is_active": rule.is_active,
        "version": rule.version,
        "effective_from": rule.effective_from.isoformat(),
        "effective_until": rule.effective_until.isoformat() if rule.effective_until else None,
        "created_at": rule.created_at.isoformat(),
    }


def _user_to_dict(user: User) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "role": user.role.value,
        "is_active": user.is_active,
        "is_verified": user.is_verified,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        "created_at": user.created_at.isoformat(),
    }
