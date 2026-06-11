"""
Decision Engine — Configurable Rules-Based Credit Decisioning
Returns: outcome, risk_category, human-readable explanation, rules_applied snapshot.
Rules are loaded from the database and cached — no code changes needed to update them.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any, Optional
import logging
import operator as op

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

logger = logging.getLogger(__name__)

# ── Decision Input ────────────────────────────────────────────────────────────

@dataclass
class DecisionInput:
    """Normalized data fed into the decision engine."""
    application_id: str
    requested_amount: Decimal
    requested_term_months: int

    # Applicant financials (decrypted for evaluation only — never persisted plaintext)
    monthly_income: Decimal
    monthly_expenses: Decimal
    employment_type: str
    employment_duration_months: int

    # Credit bureau data
    credit_score: Optional[int] = None
    negative_listings_count: int = 0
    judgements_count: int = 0
    defaults_count: int = 0
    monthly_obligations: Decimal = Decimal("0")
    enquiries_last_90_days: int = 0
    oldest_account_months: int = 0

    # Computed
    @property
    def dti_ratio(self) -> float:
        """Debt-to-income ratio: (existing obligations + new payment) / income."""
        # Estimated new monthly payment using simple interest
        estimated_payment = float(self.requested_amount) / self.requested_term_months
        total_obligations = float(self.monthly_obligations) + estimated_payment
        if float(self.monthly_income) == 0:
            return 1.0
        return total_obligations / float(self.monthly_income)

    @property
    def disposable_income(self) -> Decimal:
        return self.monthly_income - self.monthly_expenses - self.monthly_obligations


# ── Decision Output ───────────────────────────────────────────────────────────

@dataclass
class RuleResult:
    rule_id: str
    rule_name: str
    rule_type: str
    matched: bool
    outcome: Optional[str]
    explanation: str


@dataclass
class DecisionOutput:
    outcome: str                        # "approve" | "decline" | "manual_review"
    risk_category: str                  # "low" | "medium" | "high" | "very_high"
    explanation: str                    # Human-readable summary for workers/clients
    rules_applied: list[dict]           # Snapshot of all rules evaluated
    approved_amount: Optional[Decimal] = None
    approved_term_months: Optional[int] = None
    suggested_rate_percent: Optional[Decimal] = None
    triggering_rule: Optional[str] = None


# ── Operator Registry ─────────────────────────────────────────────────────────

OPERATORS = {
    ">=": op.ge, "<=": op.le,
    ">": op.gt,  "<": op.lt,
    "==": op.eq, "!=": op.ne,
}


# ── Rule Evaluator ────────────────────────────────────────────────────────────

class RuleEvaluator:
    """Evaluates a single configurable rule against a DecisionInput."""

    def evaluate(self, rule_condition: dict, decision_input: DecisionInput) -> bool:
        field_name = rule_condition["field"]
        operator_str = rule_condition["operator"]
        threshold = rule_condition["value"]

        value = self._get_field_value(field_name, decision_input)
        if value is None:
            return False

        compare = OPERATORS.get(operator_str)
        if compare is None:
            logger.warning("Unknown operator: %s", operator_str)
            return False

        try:
            return compare(float(value), float(threshold))
        except (TypeError, ValueError) as e:
            logger.error("Rule evaluation error: %s", e)
            return False

    def _get_field_value(self, field_name: str, di: DecisionInput) -> Optional[Any]:
        field_map = {
            "credit_score": di.credit_score,
            "dti_ratio": di.dti_ratio,
            "monthly_income": float(di.monthly_income),
            "disposable_income": float(di.disposable_income),
            "negative_listings_count": di.negative_listings_count,
            "judgements_count": di.judgements_count,
            "defaults_count": di.defaults_count,
            "enquiries_last_90_days": di.enquiries_last_90_days,
            "employment_duration_months": di.employment_duration_months,
            "requested_amount": float(di.requested_amount),
            "monthly_obligations": float(di.monthly_obligations),
        }
        return field_map.get(field_name)


# ── Risk Classifier ───────────────────────────────────────────────────────────

class RiskClassifier:
    """Determines risk category from credit score and negative indicators."""

    def classify(self, credit_score: Optional[int], di: DecisionInput) -> str:
        if credit_score is None:
            return "high"
        if di.judgements_count > 0 or di.defaults_count > 1:
            return "very_high"
        if credit_score >= 700 and di.negative_listings_count == 0:
            return "low"
        if credit_score >= 600 and di.negative_listings_count <= 1:
            return "medium"
        if credit_score >= 500:
            return "high"
        return "very_high"


# ── Rate Calculator ───────────────────────────────────────────────────────────

class RateCalculator:
    """Suggests an interest rate based on risk category. Configurable."""

    BASE_RATES = {
        "low": Decimal("12.50"),
        "medium": Decimal("18.00"),
        "high": Decimal("24.00"),
        "very_high": Decimal("28.00"),
    }

    def calculate(self, risk_category: str, requested_amount: Decimal) -> Decimal:
        base = self.BASE_RATES.get(risk_category, Decimal("24.00"))
        # Volume adjustment — small loans carry slightly higher rate
        if requested_amount < Decimal("5000"):
            base += Decimal("2.00")
        return base


# ── Decision Engine ───────────────────────────────────────────────────────────

class DecisionEngine:
    """
    Main decision engine. Loads rules from DB, evaluates sequentially by priority.
    First matching rule determines outcome.
    If no rule matches → manual_review (safe default).
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.evaluator = RuleEvaluator()
        self.risk_classifier = RiskClassifier()
        self.rate_calculator = RateCalculator()

    async def decide(self, decision_input: DecisionInput) -> DecisionOutput:
        """
        Run the complete decision pipeline:
        1. Load active rules ordered by priority
        2. Evaluate each rule in sequence
        3. First match → outcome
        4. Compute risk, rate, explanation
        5. Return full DecisionOutput
        """
        from app.models.models import DecisionRule

        # Load active rules ordered by priority
        result = await self.db.execute(
            select(DecisionRule)
            .where(DecisionRule.is_active == True)
            .order_by(DecisionRule.priority.asc())
        )
        rules = result.scalars().all()

        if not rules:
            logger.warning("No active decision rules found — defaulting to manual_review")
            return self._default_manual_review(decision_input, [])

        evaluated_rules: list[dict] = []
        triggering_rule = None
        outcome = "manual_review"  # safe default

        for rule in rules:
            matched = self.evaluator.evaluate(rule.condition, decision_input)
            rule_result = {
                "rule_id": str(rule.id),
                "rule_name": rule.name,
                "rule_type": rule.rule_type,
                "condition": rule.condition,
                "matched": matched,
                "action": rule.action if matched else None,
            }
            evaluated_rules.append(rule_result)

            if matched and triggering_rule is None:
                outcome = rule.action
                triggering_rule = rule.name
                logger.info(
                    "Application %s: rule '%s' triggered → %s",
                    decision_input.application_id,
                    rule.name,
                    outcome,
                )
                # Continue evaluating all rules for the snapshot, but outcome is locked

        # Classify risk
        risk_category = self.risk_classifier.classify(
            decision_input.credit_score, decision_input
        )

        # Build explanation
        explanation = self._build_explanation(
            outcome=outcome,
            risk_category=risk_category,
            decision_input=decision_input,
            triggering_rule=triggering_rule,
        )

        # Rate and amount for approvals
        approved_amount = None
        approved_term = None
        rate = None
        if outcome == "approve":
            approved_amount = decision_input.requested_amount
            approved_term = decision_input.requested_term_months
            rate = self.rate_calculator.calculate(risk_category, approved_amount)

        return DecisionOutput(
            outcome=outcome,
            risk_category=risk_category,
            explanation=explanation,
            rules_applied=evaluated_rules,
            approved_amount=approved_amount,
            approved_term_months=approved_term,
            suggested_rate_percent=rate,
            triggering_rule=triggering_rule,
        )

    def _build_explanation(
        self,
        outcome: str,
        risk_category: str,
        decision_input: DecisionInput,
        triggering_rule: Optional[str],
    ) -> str:
        score_str = (
            f"Credit score: {decision_input.credit_score}"
            if decision_input.credit_score
            else "No credit score available"
        )
        dti_str = f"Debt-to-income ratio: {decision_input.dti_ratio:.1%}"
        income_str = f"Monthly income: R{decision_input.monthly_income:,.2f}"
        negative_str = (
            f"Negative listings: {decision_input.negative_listings_count}"
            if decision_input.negative_listings_count > 0
            else "No negative listings"
        )

        if outcome == "approve":
            return (
                f"Application approved. Risk classification: {risk_category.upper()}. "
                f"{score_str}. {dti_str}. {income_str}. {negative_str}. "
                f"All eligibility criteria met."
            )
        elif outcome == "decline":
            reason = f"Triggered by rule: '{triggering_rule}'." if triggering_rule else ""
            return (
                f"Application declined. Risk classification: {risk_category.upper()}. "
                f"{score_str}. {dti_str}. {negative_str}. {reason}"
            )
        else:
            return (
                f"Application referred to manual review. Risk classification: {risk_category.upper()}. "
                f"{score_str}. {dti_str}. {income_str}. "
                f"Additional assessment required by a credit analyst."
            )

    def _default_manual_review(
        self, decision_input: DecisionInput, evaluated_rules: list
    ) -> DecisionOutput:
        return DecisionOutput(
            outcome="manual_review",
            risk_category="high",
            explanation="No decision rules configured. Referred to manual review.",
            rules_applied=evaluated_rules,
        )


# ── Default Rule Set (seeded on deployment) ───────────────────────────────────

DEFAULT_RULES = [
    # Hard declines — evaluated first (priority 1–10)
    {
        "name": "Active judgements — hard decline",
        "description": "Any active court judgement results in automatic decline",
        "rule_type": "negative_indicator",
        "condition": {"field": "judgements_count", "operator": ">", "value": 0},
        "action": "decline",
        "priority": 1,
    },
    {
        "name": "Multiple defaults — hard decline",
        "description": "More than one default results in automatic decline",
        "rule_type": "negative_indicator",
        "condition": {"field": "defaults_count", "operator": ">", "value": 1},
        "action": "decline",
        "priority": 2,
    },
    {
        "name": "Very low credit score — hard decline",
        "description": "Credit score below 400 is automatically declined",
        "rule_type": "score_threshold",
        "condition": {"field": "credit_score", "operator": "<", "value": 400},
        "action": "decline",
        "priority": 3,
    },
    {
        "name": "Income below minimum — hard decline",
        "description": "Monthly income below R3,500 is automatically declined",
        "rule_type": "income",
        "condition": {"field": "monthly_income", "operator": "<", "value": 3500},
        "action": "decline",
        "priority": 4,
    },
    {
        "name": "DTI exceeds maximum — hard decline",
        "description": "Debt-to-income ratio above 45% is automatically declined",
        "rule_type": "dti",
        "condition": {"field": "dti_ratio", "operator": ">", "value": 0.45},
        "action": "decline",
        "priority": 5,
    },
    # Auto-approvals (priority 20–30)
    {
        "name": "Excellent score — auto approve",
        "description": "Credit score 700+ with clean record — auto approved",
        "rule_type": "score_threshold",
        "condition": {"field": "credit_score", "operator": ">=", "value": 700},
        "action": "approve",
        "priority": 20,
    },
    # Manual review (priority 50+)
    {
        "name": "Moderate score — manual review",
        "description": "Credit score 450–699 referred to analyst",
        "rule_type": "score_threshold",
        "condition": {"field": "credit_score", "operator": ">=", "value": 450},
        "action": "manual_review",
        "priority": 50,
    },
    {
        "name": "High bureau enquiries — manual review",
        "description": "More than 5 enquiries in 90 days requires manual review",
        "rule_type": "enquiry_rate",
        "condition": {"field": "enquiries_last_90_days", "operator": ">", "value": 5},
        "action": "manual_review",
        "priority": 51,
    },
]
