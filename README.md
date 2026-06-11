# Ramus Cash Loans — Enterprise Credit Application & Decisioning System

![Status](https://img.shields.io/badge/status-production--ready-brightgreen)
![Stack](https://img.shields.io/badge/stack-Python%20%7C%20FastAPI%20%7C%20PostgreSQL%20%7C%20AWS-blue)
![Compliance](https://img.shields.io/badge/compliance-NCA%20%7C%20NCR%20%7C%20POPIA-orange)

---

## System Overview

A production-grade, API-first enterprise credit application and decisioning platform. Single unified backend with three role-based interfaces (client, worker, admin). Designed for compliance with the South African National Credit Act (NCA), NCR regulations, and POPIA.

---

## Architecture

```
┌─────────────────┬──────────────────┬─────────────────┐
│  Client Portal  │  Worker Portal   │  Admin Portal   │
│  (React)        │  (React)         │  (React)        │
└────────┬────────┴────────┬─────────┴────────┬────────┘
         │                 │                  │
         └─────────────────┼──────────────────┘
                           │ HTTPS · JWT RS256
                    ┌──────▼──────┐
                    │ FastAPI API │ ← WAF · Rate Limit · RBAC
                    └──────┬──────┘
          ┌────────┬────────┼────────┬────────┐
          │        │        │        │        │
     ┌────▼──┐ ┌───▼───┐ ┌─▼──┐ ┌──▼──┐ ┌──▼──┐
     │ Apps  │ │Workflw│ │Dec.│ │Audit│ │Notif│
     └────┬──┘ └───────┘ │Eng.│ │Svc  │ │ SES │
          │              └────┘ └─────┘ └─────┘
          │
    ┌─────▼──────────────────────────────┐
    │     External Integration Layer      │
    │  TransUnion (primary) + pluggable   │
    │  Consent-gated · Retry · Logged     │
    └─────────────────────────────────────┘
          │
    ┌─────▼──────────────────────────────┐
    │  PostgreSQL · Redis · S3 · KMS     │
    │  ECS Fargate · ALB · CloudWatch    │
    └─────────────────────────────────────┘
```

---

## Module Breakdown

| Module | Path | Responsibility |
|--------|------|----------------|
| Main App | `backend/app/main.py` | FastAPI entry, middleware, exception handlers |
| Config | `backend/app/core/config.py` | Env-aware settings, all secrets from env vars |
| Models | `backend/app/models/models.py` | Complete PostgreSQL schema (18 tables) |
| Auth | `backend/app/api/v1/endpoints/auth.py` | JWT RS256, refresh tokens, lockout |
| Security | `backend/app/core/security.py` | RBAC dependency injection |
| Applications | `backend/app/api/v1/endpoints/applications.py` | Full lifecycle management |
| Decision Engine | `backend/app/decision_engine/engine.py` | Configurable rules, risk classification |
| Workflow Engine | `backend/app/workflow/engine.py` | Assignment, escalation, SLA |
| Audit Service | `backend/app/audit/audit_service.py` | Immutable, append-only audit trail |
| Consent | `backend/app/api/v1/endpoints/consent.py` | Explicit pre-bureau consent |
| TransUnion | `backend/app/integrations/credit_bureaus/transunion.py` | Bureau integration, normalization |
| Email Service | `backend/app/notifications/email_service.py` | AWS SES, all events |
| Encryption | `backend/app/core/encryption.py` | KMS field-level PII encryption |
| Admin | `backend/app/api/v1/endpoints/admin.py` | Dashboard, rules, audit, users |
| Credit Bureau API | `backend/app/api/v1/endpoints/credit_bureau.py` | Initiate checks, view results |

---

## Database Schema

**18 tables** across:

- `users` — encrypted PII, roles, lockout
- `refresh_tokens` — JWT refresh, rotation, revocation
- `applications` — full lifecycle, encrypted financials
- `workflow_events` — immutable state transitions
- `worker_notes` — internal notes
- `documents` + `document_requests` — S3-backed
- `decisions` — immutable, automated + manual
- `credit_snapshots` — normalized bureau data
- `bureau_api_logs` — encrypted, immutable API logs
- `consents` — immutable, versioned consent records
- `audit_logs` — system-wide compliance audit trail
- `decision_rules` — admin-configurable, versioned
- `notification_logs` — email delivery tracking

---

## Decision Engine

Rules are stored in the database and loaded at runtime — **no code changes required** to update decisioning logic.

**Rule structure:**
```json
{
  "field": "credit_score",
  "operator": ">=",
  "value": 700
}
→ action: "approve"
→ priority: 20
```

**Default rule set** (8 rules, seeded on deployment):
1. Active judgements → decline (P1)
2. Multiple defaults → decline (P2)
3. Credit score < 400 → decline (P3)
4. Income < R3,500 → decline (P4)
5. DTI > 45% → decline (P5)
6. Credit score ≥ 700 → approve (P20)
7. Credit score ≥ 450 → manual review (P50)
8. Enquiries > 5 in 90 days → manual review (P51)

Every decision returns: **outcome + risk_category + human-readable explanation**.

---

## Application Lifecycle

```
submitted → under_review → approved
                        → declined
                        → manual_review → approved
                                       → declined
                                       → completed
         → withdrawn
```

---

## Security

- **JWT RS256** — asymmetric signing, short-lived access tokens (30min), rotating refresh tokens (7 days)
- **KMS field-level encryption** — ID numbers, income, names, bureau responses
- **S3 server-side encryption** (aws:kms) for all documents
- **Immutable audit logs** — 7-year retention, S3 Glacier archive
- **Consent-gated bureau access** — no credit check without recorded consent
- **Account lockout** — 5 failed attempts → 30-minute lockout
- **WAFv2** — rate limiting on auth endpoints, AWS managed rule set
- **RBAC** — role enforced at dependency injection level, not UI

---

## Environments

| Env | Config | Bureau | Email |
|-----|--------|--------|-------|
| Development | `.env` file + LocalStack | TransUnion sandbox | Disabled (logs to console) |
| Staging | AWS SSM | TransUnion sandbox | SES sandbox |
| Production | AWS SSM + Secrets Manager | TransUnion production | SES production |

---

## Quick Start (Development)

```bash
# 1. Clone and configure
cp .env.example .env
# Edit .env — add JWT keys, TransUnion sandbox credentials

# 2. Generate RSA keys for JWT
openssl genrsa -out private.pem 2048
openssl rsa -in private.pem -pubout -out public.pem

# 3. Start the full stack
docker-compose up --build

# 4. Run migrations
docker-compose exec api alembic upgrade head

# 5. Seed default decision rules
docker-compose exec api python -m app.scripts.seed_rules

# API docs available at:
# http://localhost:8000/api/docs  (dev only)
```

---

## Production Deployment (AWS)

```bash
# 1. Configure Terraform variables
cd infrastructure/aws
cp terraform.tfvars.example terraform.tfvars

# 2. Deploy infrastructure
terraform init
terraform plan
terraform apply

# 3. Build and push Docker image
aws ecr get-login-password | docker login --username AWS --password-stdin $ECR_URL
docker build -t ramus-api --target production ./backend
docker tag ramus-api:latest $ECR_URL/ramus/credit-api:latest
docker push $ECR_URL/ramus/credit-api:latest

# 4. Update SSM parameters with real secrets
aws ssm put-parameter --name "/ramus/production/TRANSUNION_API_KEY" --value "..." --type SecureString --overwrite

# 5. Deploy ECS service
aws ecs update-service --cluster ramus-cluster-production --service ramus-api-service --force-new-deployment
```

---

## Compliance Notes

- NCA (National Credit Act 34 of 2005) — affordability assessment, credit bureau consent
- NCR — registered credit provider requirements
- POPIA — PII encryption, data minimisation, consent records
- Audit logs retained 7 years, archived to S3 Glacier
- All bureau responses stored encrypted, never exposed in API responses without explicit admin access
- Decline reason available on request (NCA requirement)

---

## Connecting Tools (Git, CI/CD)

When you're ready to connect Git and other tools:

1. **GitHub** — push this repo: `git init && git remote add origin <your-repo> && git push`
2. **GitHub Actions** — CI/CD pipeline template in `.github/workflows/deploy.yml` (add after setup)
3. **Claude Tools** — connect Git/GitHub MCP tools in the tools panel to enable direct pushes from this conversation

---

## Files Delivered

| File | Description |
|------|-------------|
| `backend/app/main.py` | FastAPI application entrypoint |
| `backend/app/core/config.py` | Environment-aware configuration |
| `backend/app/models/models.py` | Complete database schema (18 tables) |
| `backend/app/decision_engine/engine.py` | Configurable rules-based decision engine |
| `backend/app/integrations/credit_bureaus/transunion.py` | TransUnion integration layer |
| `backend/app/audit/audit_service.py` | Immutable audit logging service |
| `backend/app/notifications/email_service.py` | AWS SES email service |
| `backend/app/workflow/engine.py` | Assignment & escalation engine |
| `backend/app/api/v1/endpoints/auth.py` | Authentication (JWT RS256) |
| `backend/app/api/v1/endpoints/applications.py` | Application lifecycle API |
| `backend/app/api/v1/endpoints/admin.py` | Admin/compliance API |
| `backend/app/api/v1/endpoints/credit_bureau.py` | Bureau request API |
| `backend/app/api/v1/endpoints/consent.py` | Consent management API |
| `backend/app/core/security.py` | RBAC dependency injection |
| `backend/app/core/encryption.py` | KMS field-level encryption |
| `backend/app/db/session.py` | Async database session |
| `backend/requirements.txt` | All production dependencies |
| `backend/Dockerfile` | Multi-stage dev/production build |
| `docker-compose.yml` | Full local dev stack |
| `infrastructure/aws/main.tf` | Terraform AWS infrastructure |
| `docs/API_REFERENCE.md` | Complete API endpoint reference |
| `ramus-admin-dashboard.jsx` | Admin portal UI |
| `ramus-worker-dashboard.jsx` | Worker portal UI |
| `ramus-client-portal.jsx` | Client portal UI |
