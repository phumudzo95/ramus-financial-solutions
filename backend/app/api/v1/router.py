"""
API v1 Router — All endpoints for client, worker, and admin roles.
Role enforcement via RBAC middleware on every protected route.
"""
from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth,
    applications,
    documents,
    decisions,
    credit_bureau,
    consent,
    workflow,
    admin,
    webhooks,
)

api_router = APIRouter()

# ── Authentication (public) ───────────────────────────────────────────────────
api_router.include_router(auth.router, prefix="/auth", tags=["authentication"])

# ── Client endpoints ──────────────────────────────────────────────────────────
api_router.include_router(applications.router, prefix="/applications", tags=["applications"])
api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
api_router.include_router(consent.router, prefix="/consent", tags=["consent"])

# ── Worker/Operations endpoints ───────────────────────────────────────────────
api_router.include_router(workflow.router, prefix="/workflow", tags=["workflow"])
api_router.include_router(decisions.router, prefix="/decisions", tags=["decisions"])
api_router.include_router(credit_bureau.router, prefix="/bureau", tags=["credit-bureau"])

# ── Admin endpoints ───────────────────────────────────────────────────────────
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])

# ── Webhook receiver (external, no auth — signature verified internally) ──────
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
