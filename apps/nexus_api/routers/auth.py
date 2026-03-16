import hashlib
import secrets
import time
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from apps.nexus_api.dependencies import (
    create_access_token,
    create_refresh_token,
    get_current_user,
    get_password_hash,
    verify_password,
)
from apps.nexus_api.security_alerts import send_security_alert
from packages.shared import metrics as metrics_emitter
from packages.shared.audit import log_audit_event
from packages.shared.config import settings
from packages.shared.db import get_db
from packages.shared.models import ApiKey, User
from packages.shared.schemas.core import ApiKeyCreate, ApiKeyOut, RefreshTokenRequest, Token

router = APIRouter()

# Simple in-memory rate limiter (15 req / minute / IP)
_rate_limits = {}


def check_rate_limit(request: Request):
    ip = request.client.host
    now = time.time()

    # Clean up old entries
    if ip in _rate_limits:
        _rate_limits[ip] = [t for t in _rate_limits[ip] if now - t < 60]

    reqs = _rate_limits.get(ip, [])
    if len(reqs) >= 15:
        raise HTTPException(status_code=429, detail="Too many requests")

    reqs.append(now)
    _rate_limits[ip] = reqs


@router.post("/login", response_model=Token)
async def login_for_access_token(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> Any:
    check_rate_limit(request)
    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalars().first()

    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email, "role": user.role}, expires_delta=access_token_expires
    )
    refresh_token = create_refresh_token(data={"sub": user.email})

    user.refresh_token_hash = get_password_hash(refresh_token)
    log_audit_event(db, "login_success", "user", user, str(user.id))
    await metrics_emitter.emit(db, "login", meta={"user_id": user.id, "role": user.role})
    await db.commit()

    return {"access_token": access_token, "token_type": "bearer", "refresh_token": refresh_token}


@router.post("/refresh", response_model=Token)
async def refresh_access_token(
    request: Request, req: RefreshTokenRequest, db: AsyncSession = Depends(get_db)
) -> Any:
    check_rate_limit(request)
    from jose import JWTError, jwt

    try:
        payload = jwt.decode(
            req.refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        email: str = payload.get("sub")
        token_type: str = payload.get("type")
        if email is None or token_type != "refresh":
            raise HTTPException(status_code=401, detail="Invalid refresh token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    res = await db.execute(select(User).where(User.email == email))
    user = res.scalars().first()

    if (
        user is None
        or not user.refresh_token_hash
        or not verify_password(req.refresh_token, user.refresh_token_hash)
    ):
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    access_token = create_access_token(data={"sub": user.email, "role": user.role})
    new_refresh_token = create_refresh_token(data={"sub": user.email})

    user.refresh_token_hash = get_password_hash(new_refresh_token)
    log_audit_event(db, "token_refresh", "user", user, str(user.id))
    await db.commit()

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "refresh_token": new_refresh_token,
    }


@router.post("/logout")
async def logout(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> Any:
    current_user.refresh_token_hash = None
    log_audit_event(db, "logout", "user", current_user, str(current_user.id))
    await db.commit()
    return {"status": "logged_out"}


from pydantic import BaseModel as _BaseModel


class _VerifyPasswordRequest(_BaseModel):
    password: str


@router.post("/verify-password")
async def verify_password_endpoint(
    payload: _VerifyPasswordRequest,
    current_user: User = Depends(get_current_user),
) -> Any:
    """Break-glass password re-verification for destructive actions."""
    if not verify_password(payload.password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid password",
        )
    return {"verified": True}


# ---------------------------------------------------------------------------
# Forgot / Reset Password
# ---------------------------------------------------------------------------

import os
from datetime import datetime, timedelta, timezone

import httpx
import structlog
from jose import jwt, JWTError

_log = structlog.get_logger(__name__)

_RESET_TOKEN_TTL = timedelta(minutes=15)
_PORTAL_ORIGIN = os.environ.get("PORTAL_ORIGIN", "https://nexus.gsmcall.com")


def _build_reset_email_html(reset_url: str, user_email: str) -> str:
    """Premium branded Nexus password-reset email (inline HTML)."""
    logo_url = f"{_PORTAL_ORIGIN}/nexus-brain.png"
    year = datetime.now(timezone.utc).year
    return f"""\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#0a0e1a;font-family:'Segoe UI',Roboto,Arial,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#0a0e1a;">
<tr><td align="center" style="padding:40px 20px;">

<!-- Card -->
<table role="presentation" width="480" cellpadding="0" cellspacing="0" style="
  background:linear-gradient(145deg,#111827,#0f172a);
  border:1px solid rgba(59,130,246,0.15);
  border-radius:16px;
  box-shadow:0 0 60px rgba(59,130,246,0.06),0 20px 40px rgba(0,0,0,0.5);
">
  <!-- Logo -->
  <tr><td align="center" style="padding:36px 40px 12px;">
    <img src="{logo_url}" alt="Nexus" width="64" height="64"
         style="display:block;border:0;outline:none;">
  </td></tr>

  <!-- Title -->
  <tr><td align="center" style="padding:0 40px 8px;">
    <h1 style="margin:0;font-size:22px;font-weight:700;
      background:linear-gradient(135deg,#3b82f6,#06b6d4);
      -webkit-background-clip:text;-webkit-text-fill-color:transparent;
      background-clip:text;letter-spacing:1px;">
      NEXUS
    </h1>
    <p style="margin:4px 0 0;color:#64748b;font-size:11px;letter-spacing:2px;text-transform:uppercase;">
      System Administration Console
    </p>
  </td></tr>

  <!-- Divider -->
  <tr><td style="padding:0 40px;">
    <div style="height:1px;background:linear-gradient(90deg,transparent,rgba(59,130,246,0.25),transparent);"></div>
  </td></tr>

  <!-- Body -->
  <tr><td style="padding:28px 40px 0;">
    <p style="margin:0 0 6px;color:#e2e8f0;font-size:15px;font-weight:600;">
      Password Reset Request
    </p>
    <p style="margin:0 0 20px;color:#94a3b8;font-size:13px;line-height:1.6;">
      We received a request to reset the password for
      <span style="color:#06b6d4;font-weight:600;">{user_email}</span>.
      Click the button below to choose a new password.
    </p>
  </td></tr>

  <!-- Button -->
  <tr><td align="center" style="padding:0 40px 24px;">
    <a href="{reset_url}" target="_blank" style="
      display:inline-block;padding:12px 36px;
      background:linear-gradient(135deg,#0891b2,#06b6d4);
      color:#ffffff;font-size:14px;font-weight:700;
      text-decoration:none;border-radius:10px;
      letter-spacing:0.5px;
      box-shadow:0 4px 14px rgba(6,182,212,0.3);
    ">Reset Password</a>
  </td></tr>

  <!-- Expiry Warning -->
  <tr><td style="padding:0 40px 24px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="
      background:rgba(245,158,11,0.06);border:1px solid rgba(245,158,11,0.15);
      border-radius:8px;
    ">
    <tr><td style="padding:10px 14px;">
      <p style="margin:0;color:#f59e0b;font-size:11px;line-height:1.5;">
        ⏱ This link expires in <strong>15 minutes</strong>.
        If you did not request this, you can safely ignore this email.
      </p>
    </td></tr>
    </table>
  </td></tr>

  <!-- Divider -->
  <tr><td style="padding:0 40px;">
    <div style="height:1px;background:linear-gradient(90deg,transparent,rgba(59,130,246,0.15),transparent);"></div>
  </td></tr>

  <!-- Footer -->
  <tr><td align="center" style="padding:20px 40px 28px;">
    <p style="margin:0;color:#475569;font-size:10px;line-height:1.5;">
      &copy; {year} Nexus &mdash; Intelligent Infrastructure Management<br>
      This is an automated message. Please do not reply.
    </p>
  </td></tr>
</table>

</td></tr>
</table>
</body>
</html>"""


class _ForgotPasswordRequest(_BaseModel):
    email: str


class _ResetPasswordRequest(_BaseModel):
    token: str
    new_password: str


@router.post("/forgot-password")
async def forgot_password(
    payload: _ForgotPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Send a password-reset email (unauthenticated, rate-limited)."""
    check_rate_limit(request)

    # Always return the same response to prevent user enumeration
    safe_response = {"ok": True, "message": "If that email exists, a reset link has been sent."}

    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalars().first()
    if not user:
        return safe_response

    # Build JWT reset token
    token_payload = {
        "sub": str(user.id),
        "purpose": "password_reset",
        "exp": datetime.now(timezone.utc) + _RESET_TOKEN_TTL,
    }
    token = jwt.encode(token_payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    reset_url = f"{_PORTAL_ORIGIN}/reset-password/{token}"

    # Build branded email
    html = _build_reset_email_html(reset_url, user.email)

    # Send via email-agent
    try:
        from apps.nexus_api.routers.brain_routes import _resolve_email_agent

        email_base, email_key = await _resolve_email_agent()
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{email_base.rstrip('/')}/email/send",
                json={
                    "to": [user.email],
                    "subject": "Nexus — Password Reset",
                    "body_text": f"Reset your Nexus password: {reset_url}\n\nThis link expires in 15 minutes.",
                    "body_html": html,
                },
                headers={"X-Service-ID": "nexus", "X-Agent-Key": email_key},
            )
            if resp.status_code != 200:
                _log.error("forgot_password_email_failed", status=resp.status_code)
    except Exception as exc:
        _log.error("forgot_password_email_error", error=str(exc)[:200])

    return safe_response


@router.post("/reset-password")
async def reset_password(
    payload: _ResetPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Reset password using a valid JWT reset token."""
    check_rate_limit(request)

    try:
        data = jwt.decode(payload.token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=400, detail="Reset link has expired or is invalid")

    if data.get("purpose") != "password_reset":
        raise HTTPException(status_code=400, detail="Invalid reset link")

    user_id = data.get("sub")
    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid reset link")

    user.password_hash = get_password_hash(payload.new_password)
    await db.commit()
    _log.info("password_reset_success", user_id=user_id)
    return {"ok": True}


@router.post("/api-keys", response_model=ApiKeyOut)
async def create_api_key(
    key_in: ApiKeyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    if current_user.role not in ["admin", "operator"]:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    raw_key = secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    db_api_key = ApiKey(
        owner_type=key_in.owner_type, owner_id=key_in.owner_id, key_hash=key_hash, name=key_in.name
    )
    db.add(db_api_key)
    log_audit_event(
        db,
        "api_key_create",
        "api_key",
        current_user,
        None,
        {"name": key_in.name, "owner_type": key_in.owner_type, "owner_id": key_in.owner_id},
    )
    await db.commit()
    await db.refresh(db_api_key)

    send_security_alert(
        "api_key_create",
        current_user.email,
        f"Key: {key_in.name} (owner: {key_in.owner_type}/{key_in.owner_id})",
    )

    # Return the raw key just once
    return ApiKeyOut.model_validate(db_api_key, update={"key": raw_key})


@router.get("/api-keys", response_model=list[ApiKeyOut])
async def list_api_keys(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """List all API keys (admin/operator only). Raw keys are never returned."""
    if current_user.role not in ["admin", "operator"]:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    res = await db.execute(select(ApiKey).order_by(ApiKey.created_at.desc()))
    return res.scalars().all()


@router.post("/api-keys/{id}/rotate", response_model=dict)
async def rotate_api_key(
    id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
) -> Any:
    if current_user.role not in ["admin", "operator"]:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    res = await db.execute(select(ApiKey).where(ApiKey.id == id))
    db_key = res.scalars().first()
    if not db_key:
        raise HTTPException(status_code=404, detail="API Key not found")

    raw_key = secrets.token_urlsafe(32)
    db_key.key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    log_audit_event(db, "api_key_rotate", "api_key", current_user, str(db_key.id))
    await db.commit()
    send_security_alert(
        "api_key_rotate",
        current_user.email,
        f"Key rotated: {db_key.name} (id: {db_key.id})",
    )
    return {"id": db_key.id, "raw_key": raw_key, "status": "rotated"}


@router.patch("/api-keys/{id}")
async def toggle_api_key(
    id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
) -> Any:
    """Toggle an API key's active status."""
    if current_user.role not in ["admin", "operator"]:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    res = await db.execute(select(ApiKey).where(ApiKey.id == id))
    db_key = res.scalars().first()
    if not db_key:
        raise HTTPException(status_code=404, detail="API Key not found")

    db_key.is_active = not db_key.is_active
    action = "api_key_enable" if db_key.is_active else "api_key_disable"
    log_audit_event(db, action, "api_key", current_user, str(db_key.id))
    await db.commit()
    send_security_alert(
        "api_key_toggle",
        current_user.email,
        f"Key {'enabled' if db_key.is_active else 'disabled'}: {db_key.name} (id: {db_key.id})",
    )
    return {"id": db_key.id, "is_active": db_key.is_active}


@router.delete("/api-keys/{id}")
async def revoke_api_key(
    id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
) -> Any:
    if current_user.role not in ["admin", "operator"]:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    res = await db.execute(select(ApiKey).where(ApiKey.id == id))
    db_key = res.scalars().first()
    if not db_key:
        raise HTTPException(status_code=404, detail="API Key not found")

    key_name = db_key.name
    await db.delete(db_key)
    log_audit_event(db, "api_key_revoke", "api_key", current_user, str(id))
    await db.commit()
    send_security_alert(
        "api_key_delete",
        current_user.email,
        f"Key deleted: {key_name} (id: {id})",
    )
    return {"status": "revoked"}
