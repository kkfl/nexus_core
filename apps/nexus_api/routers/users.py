"""
User management endpoints — admin-only CRUD.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from apps.nexus_api.dependencies import RequireRole, get_password_hash
from packages.shared.audit import log_audit_event
from packages.shared.db import get_db
from packages.shared.models import User

router = APIRouter()

require_admin = RequireRole(["admin"])


# ── Schemas ──────────────────────────────────────────────


class UserOut(BaseModel):
    id: int
    email: str
    role: str
    is_active: bool
    created_at: str

    model_config = {"from_attributes": True}

    @classmethod
    def from_user(cls, user: User) -> "UserOut":
        return cls(
            id=user.id,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at.isoformat() if user.created_at else "",
        )


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    role: str = "reader"


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    role: str | None = None
    is_active: bool | None = None


class PasswordReset(BaseModel):
    new_password: str


# ── Endpoints ────────────────────────────────────────────


@router.get("", response_model=list[UserOut])
async def list_users(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> Any:
    result = await db.execute(select(User).order_by(User.id))
    users = result.scalars().all()
    return [UserOut.from_user(u) for u in users]


@router.post("", response_model=UserOut, status_code=201)
async def create_user(
    body: UserCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> Any:
    # Check for duplicate email
    exists = await db.execute(select(User).where(User.email == body.email))
    if exists.scalars().first():
        raise HTTPException(status_code=409, detail="Email already registered")

    if body.role not in ("admin", "operator", "reader"):
        raise HTTPException(status_code=422, detail="Role must be admin, operator, or reader")

    user = User(
        email=body.email,
        password_hash=get_password_hash(body.password),
        role=body.role,
        is_active=True,
    )
    db.add(user)
    log_audit_event(
        db, "user_create", "user", admin, None, {"email": body.email, "role": body.role}
    )
    await db.commit()
    await db.refresh(user)
    return UserOut.from_user(user)


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int,
    body: UserUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> Any:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    changes: dict = {}
    if body.email is not None:
        # Check duplicate
        dup = await db.execute(select(User).where(User.email == body.email, User.id != user_id))
        if dup.scalars().first():
            raise HTTPException(status_code=409, detail="Email already in use")
        changes["email"] = body.email
        user.email = body.email

    if body.role is not None:
        if body.role not in ("admin", "operator", "reader"):
            raise HTTPException(status_code=422, detail="Role must be admin, operator, or reader")
        changes["role"] = body.role
        user.role = body.role

    if body.is_active is not None:
        changes["is_active"] = body.is_active
        user.is_active = body.is_active

    if changes:
        log_audit_event(db, "user_update", "user", admin, str(user_id), changes)
        await db.commit()
        await db.refresh(user)

    return UserOut.from_user(user)


@router.post("/{user_id}/reset-password", status_code=200)
async def reset_password(
    user_id: int,
    body: PasswordReset,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> Any:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.password_hash = get_password_hash(body.new_password)
    user.refresh_token_hash = None  # Invalidate any active sessions
    log_audit_event(db, "user_password_reset", "user", admin, str(user_id))
    await db.commit()
    return {"status": "password_reset", "user_id": user_id}
