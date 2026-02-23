"""
FastAPI dependencies for the Secrets Agent.

Service identity is established via:
  X-Service-ID: <service name, e.g. "pbx-agent">
  X-Agent-Key:  <api key value>

For V1, keys are validated via the VAULT_AGENT_KEYS environment variable
(a JSON dict: {"pbx-agent": "key123", "nexus": "nexus-key"}).
V2: replace with mTLS client certificate validation.

Admin operations additionally require role=admin from the VAULT_ADMIN_KEYS
environment variable.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import AsyncGenerator

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.secrets_agent.models import VaultPolicy
from apps.secrets_agent.policy.engine import PolicyEngine

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

_DATABASE_URL = os.environ.get("DATABASE_URL", "")
if _DATABASE_URL and _DATABASE_URL.startswith("postgresql://"):
    _DATABASE_URL = _DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

_engine = (
    create_async_engine(_DATABASE_URL, echo=False, pool_pre_ping=True) if _DATABASE_URL else None
)
_SessionLocal: async_sessionmaker | None = (
    async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False) if _engine else None
)


async def get_vault_db() -> AsyncGenerator[AsyncSession, None]:
    if _SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured.")
    async with _SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ---------------------------------------------------------------------------
# Service identity (AuthN)
# ---------------------------------------------------------------------------


def _load_agent_keys() -> dict[str, str]:
    """
    Load valid agent API keys from environment.
    VAULT_AGENT_KEYS = {"pbx-agent": "key1", "nexus": "key2", ...}
    VAULT_ADMIN_KEYS = {"admin": "admin-key"} — admin-only operations
    """
    raw = os.environ.get("VAULT_AGENT_KEYS", "{}")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def _load_admin_keys() -> dict[str, str]:
    raw = os.environ.get("VAULT_ADMIN_KEYS", "{}")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


class ServiceIdentity:
    __slots__ = ("service_id", "is_admin", "request_id", "ip_address")

    def __init__(self, service_id: str, is_admin: bool, request_id: str, ip_address: str | None):
        self.service_id = service_id
        self.is_admin = is_admin
        self.request_id = request_id
        self.ip_address = ip_address


async def get_service_identity(
    request: Request,
    x_service_id: str = Header(
        ..., alias="X-Service-ID", description="Caller's service name, e.g. 'pbx-agent'"
    ),
    x_agent_key: str = Header(
        ..., alias="X-Agent-Key", description="API key issued to the service"
    ),
) -> ServiceIdentity:
    """
    Validate service identity from headers. 401 if not recognised.
    Admin status is granted if the key is also in VAULT_ADMIN_KEYS.
    """
    agent_keys = _load_agent_keys()
    admin_keys = _load_admin_keys()

    expected = agent_keys.get(x_service_id)
    # Also accept admin keys for full access
    is_admin = admin_keys.get(x_service_id) == x_agent_key

    if expected != x_agent_key and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid service identity or API key.",
        )

    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    ip = request.client.host if request.client else None
    return ServiceIdentity(
        service_id=x_service_id, is_admin=is_admin, request_id=request_id, ip_address=ip
    )


def require_admin(identity: ServiceIdentity = Depends(get_service_identity)) -> ServiceIdentity:
    if not identity.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required.")
    return identity


# ---------------------------------------------------------------------------
# Policy engine (loaded fresh per request — small table, safe for V1)
# ---------------------------------------------------------------------------


async def get_policy_engine(db: AsyncSession = Depends(get_vault_db)) -> PolicyEngine:
    result = await db.execute(select(VaultPolicy).where(VaultPolicy.is_active.is_(True)))
    policies = list(result.scalars().all())
    return PolicyEngine(policies)
