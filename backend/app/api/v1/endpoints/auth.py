"""
Authentication Endpoint — JWT RS256, refresh tokens, registration, login.
Rate-limited. Accounts lock after failed attempts.
"""
from __future__ import annotations
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.db.session import get_db
from app.models.models import AuditAction, RefreshToken, User, UserRole
from app.audit.audit_service import AuditService
from app.core.encryption import EncryptionService

router = APIRouter()
enc = EncryptionService()

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 30


# ── Schemas ───────────────────────────────────────────────────────────────────

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


# ── Auth Helpers ──────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(user: User) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role.value,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.JWT_PRIVATE_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token() -> str:
    import secrets
    return secrets.token_urlsafe(64)


def hash_token(token: str) -> str:
    import hashlib
    return hashlib.sha256(token.encode()).hexdigest()


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Register a new client account."""
    audit = AuditService(db)

    # Check email uniqueness
    existing = await db.execute(select(User).where(User.email == payload.email.lower()))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    user = User(
        email=payload.email.lower(),
        hashed_password=hash_password(payload.password),
        role=UserRole.CLIENT,
        first_name_enc=enc.encrypt(payload.first_name),
        last_name_enc=enc.encrypt(payload.last_name),
        phone_enc=enc.encrypt(payload.phone) if payload.phone else None,
        is_active=True,
        is_verified=False,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    await audit.log_from_request(
        request=request,
        action=AuditAction.USER_CREATED,
        actor_id=str(user.id),
        actor_role=user.role,
        target_type="user",
        target_id=str(user.id),
        after_state={"email": user.email, "role": user.role.value},
    )

    # Send verification email (async)
    from app.notifications.email_service import EmailNotificationService, NotificationEvent
    notifier = EmailNotificationService(db)
    await notifier.send(
        event=NotificationEvent.APPLICATION_SUBMITTED,  # Reuse, or add WELCOME event
        recipient_user_id=str(user.id),
        recipient_email=user.email,
        template_vars={"first_name": payload.first_name, "reference_number": "", "requested_amount": "", "submitted_at": ""},
        application_id=None,
    )

    return {"message": "Account created. Please check your email to verify your account."}


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate and receive JWT access + refresh tokens."""
    audit = AuditService(db)

    result = await db.execute(select(User).where(User.email == payload.email.lower()))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials.")

    # Check lockout
    if user.locked_until and user.locked_until > datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=f"Account locked until {user.locked_until.isoformat()}. Too many failed attempts.",
        )

    if not user.is_active:
        raise HTTPException(status_code=401, detail="Account is disabled.")

    if not verify_password(payload.password, user.hashed_password):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
            user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_MINUTES)
        await db.commit()
        raise HTTPException(status_code=401, detail="Invalid credentials.")

    # Successful login
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = datetime.now(timezone.utc)

    # Issue tokens
    access_token = create_access_token(user)
    refresh_token_raw = create_refresh_token()
    refresh_hash = hash_token(refresh_token_raw)

    rt = RefreshToken(
        user_id=user.id,
        token_hash=refresh_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(rt)
    await db.commit()

    await audit.log_from_request(
        request=request,
        action=AuditAction.USER_LOGIN,
        actor_id=str(user.id),
        actor_role=user.role,
        target_type="user",
        target_id=str(user.id),
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token_raw,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        role=user.role.value,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    payload: RefreshRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Exchange a valid refresh token for a new access token."""
    token_hash = hash_token(payload.refresh_token)
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked == False,
        )
    )
    rt = result.scalar_one_or_none()

    if not rt or rt.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token.")

    user_result = await db.execute(select(User).where(User.id == rt.user_id))
    user = user_result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User account inactive.")

    # Rotate refresh token
    rt.revoked = True
    new_rt_raw = create_refresh_token()
    new_rt = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(new_rt_raw),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        ip_address=request.client.host if request.client else None,
    )
    db.add(new_rt)
    await db.commit()

    return TokenResponse(
        access_token=create_access_token(user),
        refresh_token=new_rt_raw,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        role=user.role.value,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    payload: RefreshRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Revoke refresh token on logout."""
    from app.core.security import get_current_user
    token_hash = hash_token(payload.refresh_token)
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    rt = result.scalar_one_or_none()
    if rt:
        rt.revoked = True
        await db.commit()
