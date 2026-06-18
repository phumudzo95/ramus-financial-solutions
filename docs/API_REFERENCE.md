# Ramus Credit System — API Reference

> **Developer Documentation Only**
> This file is for backend developers and system integrators. It is not linked from any user-facing page.

---

## Base URL

```
https://api.ramusfinancialsolutions.co.za/api/v1
```

All endpoints require a valid JWT RS256 bearer token unless otherwise stated.

---

## Authentication

### POST `/auth/login`
Authenticate a user and receive access + refresh tokens.

**Request:**
```json
{
  "email": "user@ramusfinancialsolutions.co.za",
  "password": "secure_password"
}
```

**Response:**
```json
{
  "access_token": "<JWT>",
  "refresh_token": "<JWT>",
  "token_type": "bearer",
  "expires_in": 900
}
```

### POST `/auth/refresh`
Exchange a refresh token for a new access token.

### POST `/auth/logout`
Revoke the current refresh token.

---

## Applications

### POST `/applications`
Submit a new credit application.

### GET `/applications`
List applications (role-filtered). Admins see all; workers see assigned; clients see their own.

### GET `/applications/{id}`
Get full application detail.

### PATCH `/applications/{id}/status`
Update application status (worker/admin only).

---

## Documents

### POST `/documents/upload`
Upload a document to S3 (pre-signed URL flow).

### GET `/documents/{application_id}`
List all documents for an application.

### PATCH `/documents/{id}/verify`
Mark a document as verified or rejected (worker/admin only).

---

## Credit Bureau

### POST `/credit-bureau/initiate`
Initiate a TransUnion credit check. Requires prior consent record.

### GET `/credit-bureau/results/{application_id}`
Retrieve normalised bureau results for an application.

---

## Decisions

### GET `/decisions/{application_id}`
Retrieve the decision for an application.

### POST `/decisions/manual`
Submit a manual decision (worker/admin only). Immutable once recorded.

---

## Decision Rules (Admin Only)

### GET `/admin/rules`
List all decision rules.

### POST `/admin/rules`
Create a new decision rule.

### PATCH `/admin/rules/{id}`
Update a rule.

### DELETE `/admin/rules/{id}`
Soft-delete a rule.

---

## Admin

### GET `/admin/stats`
System overview statistics.

### GET `/admin/users`
List all user accounts.

### POST `/admin/users`
Create a new user account.

---

## Audit

### GET `/admin/audit`
Retrieve audit log entries (paginated, filterable by action type and date range).

---

## Webhooks

### POST `/webhooks/transunion`
Callback endpoint for asynchronous TransUnion bureau responses.

---

## Error Codes

| Code | Meaning |
|------|---------|
| 401 | Unauthenticated — invalid or expired token |
| 403 | Forbidden — insufficient role |
| 404 | Resource not found |
| 409 | Conflict — e.g. duplicate application |
| 422 | Validation error |
| 429 | Rate limit exceeded |
| 500 | Internal server error |

---

## Tech Stack

- **Framework:** FastAPI (Python 3.11)
- **Auth:** JWT RS256 (asymmetric keys)
- **Database:** PostgreSQL via Supabase
- **Storage:** AWS S3 (document storage)
- **Encryption:** AWS KMS (field-level PII encryption)
- **Credit Bureau:** TransUnion SA
- **Email:** AWS SES
- **Infrastructure:** ECS Fargate + ALB

---

*Last updated: June 2026*
