import hashlib
import secrets
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from packages.shared.db import get_db
from packages.shared.models import User, ApiKey
from packages.shared.schemas.core import Token, ApiKeyCreate, ApiKeyOut, RefreshTokenRequest
from packages.shared.config import settings
from apps.nexus_api.dependencies import verify_password, create_access_token, create_refresh_token, get_password_hash, get_current_user
from packages.shared.audit import log_audit_event
from packages.shared import metrics as metrics_emitter
from fastapi import Request
import time

router = APIRouter()

# Simple in-memory rate limiter (5 req / minute / IP)
_rate_limits = {}

def check_rate_limit(request: Request):
    ip = request.client.host
    now = time.time()
    
    # Clean up old entries
    if ip in _rate_limits:
        _rate_limits[ip] = [t for t in _rate_limits[ip] if now - t < 60]
        
    reqs = _rate_limits.get(ip, [])
    if len(reqs) >= 5:
        raise HTTPException(status_code=429, detail="Too many requests")
        
    reqs.append(now)
    _rate_limits[ip] = reqs

@router.post("/login", response_model=Token)
async def login_for_access_token(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
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
    request: Request,
    req: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db)
) -> Any:
    check_rate_limit(request)
    from jose import jwt, JWTError
    from pydantic import ValidationError
    
    try:
        payload = jwt.decode(req.refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email: str = payload.get("sub")
        token_type: str = payload.get("type")
        if email is None or token_type != "refresh":
            raise HTTPException(status_code=401, detail="Invalid refresh token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    res = await db.execute(select(User).where(User.email == email))
    user = res.scalars().first()
    
    if user is None or not user.refresh_token_hash or not verify_password(req.refresh_token, user.refresh_token_hash):
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    access_token = create_access_token(data={"sub": user.email, "role": user.role})
    new_refresh_token = create_refresh_token(data={"sub": user.email})
    
    user.refresh_token_hash = get_password_hash(new_refresh_token)
    log_audit_event(db, "token_refresh", "user", user, str(user.id))
    await db.commit()
    
    return {"access_token": access_token, "token_type": "bearer", "refresh_token": new_refresh_token}

@router.post("/logout")
async def logout(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    current_user.refresh_token_hash = None
    log_audit_event(db, "logout", "user", current_user, str(current_user.id))
    await db.commit()
    return {"status": "logged_out"}

@router.post("/api-keys", response_model=ApiKeyOut)
async def create_api_key(
    key_in: ApiKeyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    if current_user.role not in ['admin', 'operator']:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    raw_key = secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    
    db_api_key = ApiKey(
        owner_type=key_in.owner_type,
        owner_id=key_in.owner_id,
        key_hash=key_hash,
        name=key_in.name
    )
    db.add(db_api_key)
    log_audit_event(db, "api_key_create", "api_key", current_user, None, {"name": key_in.name, "owner_type": key_in.owner_type, "owner_id": key_in.owner_id})
    await db.commit()
    await db.refresh(db_api_key)
    
    # Return the raw key just once
    return ApiKeyOut.model_validate(db_api_key, update={"key": raw_key})

@router.post("/api-keys/{id}/rotate", response_model=dict)
async def rotate_api_key(
    id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    if current_user.role not in ['admin', 'operator']:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    res = await db.execute(select(ApiKey).where(ApiKey.id == id))
    db_key = res.scalars().first()
    if not db_key:
        raise HTTPException(status_code=404, detail="API Key not found")
        
    raw_key = secrets.token_urlsafe(32)
    db_key.key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    log_audit_event(db, "api_key_rotate", "api_key", current_user, str(db_key.id))
    await db.commit()
    return {"id": db_key.id, "raw_key": raw_key, "status": "rotated"}

@router.delete("/api-keys/{id}")
async def revoke_api_key(
    id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    if current_user.role not in ['admin', 'operator']:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    res = await db.execute(select(ApiKey).where(ApiKey.id == id))
    db_key = res.scalars().first()
    if not db_key:
        raise HTTPException(status_code=404, detail="API Key not found")
        
    # We do a hard delete or archive, let's delete
    await db.delete(db_key)
    log_audit_event(db, "api_key_revoke", "api_key", current_user, str(id))
    await db.commit()
    return {"status": "revoked"}
