"""
Email Notification Service — AWS SES Only
No SMS, no push, no other channels.
All notifications are email-only per system requirements.
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from string import Template
from typing import Optional

import boto3
from botocore.exceptions import ClientError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.models import NotificationEvent, NotificationLog

logger = logging.getLogger(__name__)


# ── Email Templates ───────────────────────────────────────────────────────────

EMAIL_TEMPLATES: dict[str, dict] = {
    "application_submitted": {
        "subject": "Application Received — Ramus Cash Loans",
        "body_html": """
<html><body style="font-family:Arial,sans-serif;color:#1a1a2e;max-width:600px;margin:0 auto">
<div style="background:#0a2463;padding:20px;text-align:center">
  <h1 style="color:#FFD700;margin:0">Ramus Cash Loans</h1>
</div>
<div style="padding:30px">
  <h2>Application Received</h2>
  <p>Dear $first_name,</p>
  <p>We have received your loan application <strong>$reference_number</strong> for
  <strong>R$requested_amount</strong>.</p>
  <p>Our team will review your application and you will be notified of any updates via email.</p>
  <div style="background:#f5f5f5;padding:15px;border-radius:5px;margin:20px 0">
    <strong>Reference Number:</strong> $reference_number<br>
    <strong>Amount Requested:</strong> R$requested_amount<br>
    <strong>Submitted:</strong> $submitted_at
  </div>
  <p>If you have any questions, please contact us at <a href="mailto:support@ramuscashloans.co.za">
  support@ramuscashloans.co.za</a></p>
</div>
<div style="background:#0a2463;padding:15px;text-align:center;color:#aaa;font-size:12px">
  <p style="color:#aaa">Ramus Cash Loans — Registered Credit Provider | NCR Registration: NCRCP XXXX</p>
</div>
</body></html>""",
    },
    "status_changed": {
        "subject": "Application Update — Ramus Cash Loans (Ref: $reference_number)",
        "body_html": """
<html><body style="font-family:Arial,sans-serif;color:#1a1a2e;max-width:600px;margin:0 auto">
<div style="background:#0a2463;padding:20px;text-align:center">
  <h1 style="color:#FFD700;margin:0">Ramus Cash Loans</h1>
</div>
<div style="padding:30px">
  <h2>Application Status Update</h2>
  <p>Dear $first_name,</p>
  <p>Your loan application <strong>$reference_number</strong> status has been updated.</p>
  <div style="background:#f5f5f5;padding:15px;border-radius:5px;margin:20px 0">
    <strong>New Status:</strong> $new_status<br>
    <strong>Updated:</strong> $updated_at
  </div>
  <p>$status_message</p>
</div>
<div style="background:#0a2463;padding:15px;text-align:center;font-size:12px">
  <p style="color:#aaa">Ramus Cash Loans — Registered Credit Provider</p>
</div>
</body></html>""",
    },
    "approved": {
        "subject": "Congratulations! Your Application is Approved — Ramus Cash Loans",
        "body_html": """
<html><body style="font-family:Arial,sans-serif;color:#1a1a2e;max-width:600px;margin:0 auto">
<div style="background:#0a2463;padding:20px;text-align:center">
  <h1 style="color:#FFD700;margin:0">Ramus Cash Loans</h1>
</div>
<div style="padding:30px">
  <h2 style="color:#27ae60">Application Approved!</h2>
  <p>Dear $first_name,</p>
  <p>We are pleased to inform you that your loan application has been <strong>approved</strong>.</p>
  <div style="background:#eafaf1;border-left:4px solid #27ae60;padding:15px;margin:20px 0">
    <strong>Approved Amount:</strong> R$approved_amount<br>
    <strong>Term:</strong> $approved_term_months months<br>
    <strong>Interest Rate:</strong> $approved_rate_percent% per annum<br>
    <strong>Reference:</strong> $reference_number
  </div>
  <p>A consultant will be in touch with you shortly to finalise the agreement.</p>
</div>
<div style="background:#0a2463;padding:15px;text-align:center;font-size:12px">
  <p style="color:#aaa">Ramus Cash Loans — Registered Credit Provider</p>
</div>
</body></html>""",
    },
    "declined": {
        "subject": "Application Decision — Ramus Cash Loans (Ref: $reference_number)",
        "body_html": """
<html><body style="font-family:Arial,sans-serif;color:#1a1a2e;max-width:600px;margin:0 auto">
<div style="background:#0a2463;padding:20px;text-align:center">
  <h1 style="color:#FFD700;margin:0">Ramus Cash Loans</h1>
</div>
<div style="padding:30px">
  <h2>Application Decision</h2>
  <p>Dear $first_name,</p>
  <p>After careful consideration, we are unable to approve your loan application
  <strong>$reference_number</strong> at this time.</p>
  <p>You are entitled to know the reason for this decision. Please contact us at
  <a href="mailto:support@ramuscashloans.co.za">support@ramuscashloans.co.za</a>
  or call 0800 XXX XXX to request this information.</p>
  <p>You may reapply after 90 days or if your financial circumstances change.</p>
  <p>As a registered credit provider, we are required to inform you that you may
  contact the National Credit Regulator (NCR) if you have concerns about this decision.</p>
</div>
<div style="background:#0a2463;padding:15px;text-align:center;font-size:12px">
  <p style="color:#aaa">Ramus Cash Loans — NCR Registration: NCRCP XXXX</p>
</div>
</body></html>""",
    },
    "document_requested": {
        "subject": "Additional Documents Required — Ramus Cash Loans (Ref: $reference_number)",
        "body_html": """
<html><body style="font-family:Arial,sans-serif;color:#1a1a2e;max-width:600px;margin:0 auto">
<div style="background:#0a2463;padding:20px;text-align:center">
  <h1 style="color:#FFD700;margin:0">Ramus Cash Loans</h1>
</div>
<div style="padding:30px">
  <h2>Additional Documents Required</h2>
  <p>Dear $first_name,</p>
  <p>To process your application <strong>$reference_number</strong>, we require the following:</p>
  <div style="background:#fff3cd;border-left:4px solid #FFD700;padding:15px;margin:20px 0">
    <strong>Document Type:</strong> $document_type<br>
    <strong>Reason:</strong> $reason<br>
    <strong>Required By:</strong> $due_date
  </div>
  <p>Please upload this document by logging into your account at
  <a href="$portal_url">$portal_url</a></p>
</div>
<div style="background:#0a2463;padding:15px;text-align:center;font-size:12px">
  <p style="color:#aaa">Ramus Cash Loans — Registered Credit Provider</p>
</div>
</body></html>""",
    },
    "manual_review_assigned": {
        "subject": "Application Under Review — Ramus Cash Loans (Ref: $reference_number)",
        "body_html": """
<html><body style="font-family:Arial,sans-serif;color:#1a1a2e;max-width:600px;margin:0 auto">
<div style="background:#0a2463;padding:20px;text-align:center">
  <h1 style="color:#FFD700;margin:0">Ramus Cash Loans</h1>
</div>
<div style="padding:30px">
  <h2>Application Under Review</h2>
  <p>Dear $first_name,</p>
  <p>Your application <strong>$reference_number</strong> has been assigned to a credit analyst
  for detailed review. This typically takes 1–2 business days.</p>
  <p>You will be notified by email once a decision has been made.</p>
</div>
<div style="background:#0a2463;padding:15px;text-align:center;font-size:12px">
  <p style="color:#aaa">Ramus Cash Loans — Registered Credit Provider</p>
</div>
</body></html>""",
    },
}

STATUS_MESSAGES = {
    "under_review": "Your application is currently being reviewed by our team.",
    "manual_review": "Your application has been referred to a credit analyst for detailed review.",
    "approved": "Your application has been approved! A consultant will contact you shortly.",
    "declined": "We are unable to approve your application at this time.",
    "completed": "Your application process is complete.",
}


# ── Notification Service ──────────────────────────────────────────────────────

class EmailNotificationService:
    """
    Email-only notification service using AWS SES.
    All notifications go through this service — no other channels permitted.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self._ses = boto3.client("ses", region_name=settings.AWS_SES_REGION) if settings.EMAIL_ENABLED else None

    async def send(
        self,
        event: NotificationEvent,
        recipient_user_id: str,
        recipient_email: str,
        template_vars: dict,
        application_id: Optional[str] = None,
    ) -> bool:
        """
        Send an email notification for a given event.
        Logs every send attempt regardless of success.
        """
        template_name = event.value
        template = EMAIL_TEMPLATES.get(template_name)
        if not template:
            logger.error("No email template found for event: %s", template_name)
            return False

        try:
            subject = Template(template["subject"]).safe_substitute(template_vars)
            body_html = Template(template["body_html"]).safe_substitute(template_vars)
        except KeyError as e:
            logger.error("Template variable missing: %s for event %s", e, template_name)
            return False

        ses_message_id = None
        status = "sent"
        error_message = None

        if settings.EMAIL_ENABLED and self._ses:
            try:
                send_args = {
                    "Source": f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM_ADDRESS}>",
                    "Destination": {"ToAddresses": [recipient_email]},
                    "Message": {
                        "Subject": {"Data": subject, "Charset": "UTF-8"},
                        "Body": {"Html": {"Data": body_html, "Charset": "UTF-8"}},
                    },
                }
                if settings.AWS_SES_CONFIGURATION_SET:
                    send_args["ConfigurationSetName"] = settings.AWS_SES_CONFIGURATION_SET

                response = self._ses.send_email(**send_args)
                ses_message_id = response.get("MessageId")
                logger.info(
                    "Email sent: event=%s to=%s ses_id=%s",
                    event.value, recipient_email, ses_message_id,
                )
            except ClientError as e:
                status = "failed"
                error_message = str(e)
                logger.error("SES send failed: %s | to=%s | event=%s", e, recipient_email, event.value)
        else:
            logger.info("[EMAIL DISABLED] Would send: event=%s to=%s", event.value, recipient_email)

        # Always log the notification attempt
        import uuid as _uuid
        log = NotificationLog(
            recipient_user_id=_uuid.UUID(recipient_user_id),
            recipient_email=recipient_email,
            event=event,
            application_id=_uuid.UUID(application_id) if application_id else None,
            subject=subject,
            template_name=template_name,
            ses_message_id=ses_message_id,
            status=status,
            error_message=error_message,
            sent_at=datetime.now(timezone.utc) if status == "sent" else None,
        )
        self.db.add(log)
        await self.db.flush()

        return status == "sent"

    # ── Convenience Methods ───────────────────────────────────────────────────

    async def notify_application_submitted(
        self, user_id: str, email: str, first_name: str,
        reference_number: str, requested_amount: str, application_id: str
    ):
        await self.send(
            event=NotificationEvent.APPLICATION_SUBMITTED,
            recipient_user_id=user_id,
            recipient_email=email,
            application_id=application_id,
            template_vars={
                "first_name": first_name,
                "reference_number": reference_number,
                "requested_amount": requested_amount,
                "submitted_at": datetime.now(timezone.utc).strftime("%d %B %Y %H:%M UTC"),
            },
        )

    async def notify_status_change(
        self, user_id: str, email: str, first_name: str,
        reference_number: str, new_status: str, application_id: str
    ):
        await self.send(
            event=NotificationEvent.STATUS_CHANGED,
            recipient_user_id=user_id,
            recipient_email=email,
            application_id=application_id,
            template_vars={
                "first_name": first_name,
                "reference_number": reference_number,
                "new_status": new_status.replace("_", " ").title(),
                "updated_at": datetime.now(timezone.utc).strftime("%d %B %Y %H:%M UTC"),
                "status_message": STATUS_MESSAGES.get(new_status, ""),
            },
        )

    async def notify_approved(
        self, user_id: str, email: str, first_name: str,
        reference_number: str, approved_amount: str,
        approved_term_months: int, approved_rate_percent: str,
        application_id: str,
    ):
        await self.send(
            event=NotificationEvent.APPROVED,
            recipient_user_id=user_id,
            recipient_email=email,
            application_id=application_id,
            template_vars={
                "first_name": first_name,
                "reference_number": reference_number,
                "approved_amount": approved_amount,
                "approved_term_months": approved_term_months,
                "approved_rate_percent": approved_rate_percent,
            },
        )

    async def notify_declined(
        self, user_id: str, email: str, first_name: str,
        reference_number: str, application_id: str,
    ):
        await self.send(
            event=NotificationEvent.DECLINED,
            recipient_user_id=user_id,
            recipient_email=email,
            application_id=application_id,
            template_vars={
                "first_name": first_name,
                "reference_number": reference_number,
            },
        )

    async def notify_document_requested(
        self, user_id: str, email: str, first_name: str,
        reference_number: str, document_type: str, reason: str,
        due_date: str, application_id: str, portal_url: str,
    ):
        await self.send(
            event=NotificationEvent.DOCUMENT_REQUESTED,
            recipient_user_id=user_id,
            recipient_email=email,
            application_id=application_id,
            template_vars={
                "first_name": first_name,
                "reference_number": reference_number,
                "document_type": document_type.replace("_", " ").title(),
                "reason": reason,
                "due_date": due_date,
                "portal_url": portal_url,
            },
        )

    async def notify_manual_review(
        self, user_id: str, email: str, first_name: str,
        reference_number: str, application_id: str,
    ):
        await self.send(
            event=NotificationEvent.MANUAL_REVIEW_ASSIGNED,
            recipient_user_id=user_id,
            recipient_email=email,
            application_id=application_id,
            template_vars={
                "first_name": first_name,
                "reference_number": reference_number,
            },
        )
