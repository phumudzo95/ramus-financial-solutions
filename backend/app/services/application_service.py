"""
Application Service — orchestrates the full loan application lifecycle.
"""
from __future__ import annotations
import uuid
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.models import (
    Application, ApplicationStatus, Decision, DecisionOutcome,
    DecisionRule, CreditSnapshot, User, UserRole,
    AuditAction, RiskCategory,
)
from app.decision_engine.engine import DecisionEngine
from app.workflow.engine import WorkflowEngine
from app.audit.audit_service import AuditService
from app.notifications.email_service import EmailNotificationService
from app.core.encryption import EncryptionService
from app.core.exceptions import NotFoundException, ApplicationException

logger = logging.getLogger(__name__)
enc = EncryptionService()


class ApplicationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.decision_engine = DecisionEngine(db)
        self.workflow_engine = WorkflowEngine(db)
        self.audit = AuditService(db)
        self.email = EmailNotificationService()

    async def run_decision(
        self,
        application_id: uuid.UUID,
        actor_id: uuid.UUID,
        credit_snapshot_id: Optional[uuid.UUID] = None,
    ) -> Decision:
        """Run automated decision for an application."""
        result = await self.db.execute(
            select(Application).where(Application.id == application_id)
        )
        app = result.scalar_one_or_none()
        if not app:
            raise NotFoundException(f"Application {application_id} not found")

        # Decrypt income fields for decision engine
        monthly_income = 0.0
        monthly_expenses = 0.0
        try:
            if app.monthly_income_enc:
                monthly_income = float(enc.decrypt(app.monthly_income_enc))
            if app.monthly_expenses_enc:
                monthly_expenses = float(enc.decrypt(app.monthly_expenses_enc))
        except Exception:
            logger.warning("Could not decrypt income fields for application %s", application_id)

        snapshot = None
        if credit_snapshot_id:
            snap_result = await self.db.execute(
                select(CreditSnapshot).where(CreditSnapshot.id == credit_snapshot_id)
            )
            snapshot = snap_result.scalar_one_or_none()

        rules_result = await self.db.execute(
            select(DecisionRule)
            .where(DecisionRule.is_active == True)
            .order_by(DecisionRule.priority)
        )
        rules = rules_result.scalars().all()

        input_data = {
            "requested_amount": float(app.requested_amount),
            "requested_term_months": app.requested_term_months,
            "monthly_income": monthly_income,
            "monthly_expenses": monthly_expenses,
            "employment_type": app.employment_type or "employed",
            "employment_duration_months": app.employment_duration_months or 0,
        }
        if snapshot:
            input_data.update({
                "credit_score": snapshot.credit_score or 0,
                "negative_listings_count": snapshot.negative_listings_count or 0,
                "judgements_count": snapshot.judgements_count or 0,
                "total_outstanding_debt": float(snapshot.total_outstanding_debt or 0),
                "monthly_obligations": float(snapshot.monthly_obligations or 0),
                "enquiries_last_90_days": snapshot.enquiries_last_90_days or 0,
            })

        outcome, risk_category, explanation, rules_applied = await self.decision_engine.evaluate(
            input_data, rules
        )

        approved_amount = None
        approved_term = None
        approved_rate = None
        if outcome == DecisionOutcome.APPROVE:
            approved_amount = app.requested_amount
            approved_term = app.requested_term_months
            rate_map = {
                RiskCategory.LOW: Decimal("18.00"),
                RiskCategory.MEDIUM: Decimal("24.00"),
                RiskCategory.HIGH: Decimal("30.00"),
                RiskCategory.VERY_HIGH: Decimal("36.00"),
            }
            approved_rate = rate_map.get(risk_category, Decimal("24.00"))

        decision = Decision(
            id=uuid.uuid4(),
            application_id=application_id,
            made_by_id=None,
            is_automated=True,
            outcome=outcome,
            risk_category=risk_category,
            explanation=explanation,
            rules_applied=rules_applied,
            credit_snapshot_id=credit_snapshot_id,
            approved_amount=approved_amount,
            approved_term_months=approved_term,
            approved_rate_percent=approved_rate,
            is_override=False,
        )
        self.db.add(decision)

        status_map = {
            DecisionOutcome.APPROVE: ApplicationStatus.APPROVED,
            DecisionOutcome.DECLINE: ApplicationStatus.DECLINED,
            DecisionOutcome.MANUAL_REVIEW: ApplicationStatus.MANUAL_REVIEW,
        }
        old_status = app.status
        app.status = status_map[outcome]
        await self.db.flush()

        await self.audit.log(
            action=AuditAction.DECISION_MADE,
            actor_id=actor_id,
            target_type="application",
            target_id=application_id,
            before_state={"status": old_status.value},
            after_state={"status": app.status.value, "outcome": outcome.value},
        )

        if outcome == DecisionOutcome.MANUAL_REVIEW:
            try:
                await self.workflow_engine.assign_application(application_id)
            except Exception as e:
                logger.warning("Auto-assignment failed: %s", e)

        try:
            user_result = await self.db.execute(select(User).where(User.id == app.applicant_id))
            user = user_result.scalar_one_or_none()
            if user:
                await self.email.send_status_update(
                    recipient_email=user.email,
                    applicant_name=f"{user.first_name} {user.last_name}",
                    reference_number=app.reference_number,
                    new_status=app.status.value,
                    outcome=outcome.value,
                )
        except Exception as e:
            logger.warning("Failed to send decision email: %s", e)

        return decision
