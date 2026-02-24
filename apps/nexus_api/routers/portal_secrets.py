from __future__ import annotations

import datetime
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from apps.nexus_api.dependencies import RequireRole, get_current_user, verify_password
from packages.shared.client.agent_registry import get_registry_client
from packages.shared.models.core import User

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class PortalSecretCreate(BaseModel):
    alias: str
    tenant_id: str
    env: str
    value: str
    description: str | None = None
    scope_tags: list[Any] | None = None
    rotation_interval_days: int | None = None


class PortalSecretUpdate(BaseModel):
    description: str | None = None
    scope_tags: list[Any] | None = None
    rotation_interval_days: int | None = None


class PortalSecretRotate(BaseModel):
    new_value: str
    reason: str | None = None


class PortalSecretRevealRequest(BaseModel):
    password: str
    reason: str
    tenant_id: str
    env: str


class PortalSecretRevealResponse(BaseModel):
    id: str
    alias: str
    tenant_id: str
    env: str
    value: str
    expires_in_seconds: int = 120


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def get_secrets_agent_url() -> str:
    registry = get_registry_client()
    agent = await registry.resolve_agent("secrets-agent", tenant_id=None, env="prod")
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Secrets Agent not found in registry",
        )
    return agent.base_url


import os


# ...
async def proxy_request(
    method: str,
    path: str,
    params: dict[str, Any] | None = None,
    json_data: dict[str, Any] | None = None,
) -> Any:
    base_url = await get_secrets_agent_url()
    url = f"{base_url.rstrip('/')}{path}"

    service_id = os.environ.get("NEXUS_VAULT_SERVICE_ID", "nexus")
    agent_key = os.environ.get("NEXUS_VAULT_AGENT_KEY", "nexus-internal-key")

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.request(
                method,
                url,
                params=params,
                json=json_data,
                headers={
                    "X-Service-ID": service_id,
                    "X-Agent-Key": agent_key,
                    "Content-Type": "application/json",
                },
            )
            if resp.status_code >= 400:
                # Try to propagate error detail
                try:
                    detail = resp.json().get("detail", resp.text)
                except Exception:
                    detail = resp.text
                raise HTTPException(status_code=resp.status_code, detail=detail)
            return resp.json() if resp.content else None
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Error connecting to secrets-agent: {exc}",
            )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=list[dict[str, Any]])
async def list_portal_secrets(
    tenant_id: str | None = Query(None),
    env: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(RequireRole(["admin", "operator", "BreakGlass"])),
) -> Any:
    """List secrets metadata via secrets_agent proxy."""
    return await proxy_request(
        "GET",
        "/v1/secrets",
        params={"tenant_id": tenant_id, "env": env, "skip": skip, "limit": limit},
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_portal_secret(
    payload: PortalSecretCreate,
    current_user: User = Depends(RequireRole(["admin", "operator"])),
) -> Any:
    """Create secret in secrets_agent."""
    return await proxy_request("POST", "/v1/secrets", json_data=payload.model_dump())


@router.get("/{id_or_alias}", response_model=dict[str, Any])
async def get_portal_secret(
    id_or_alias: str,
    tenant_id: str | None = Query(None),
    env: str | None = Query(None),
    current_user: User = Depends(RequireRole(["admin", "operator", "BreakGlass"])),
) -> Any:
    """Get secret metadata. Note: if id_or_alias is alias, tenant_id and env are required."""
    # secrets_agent GET /{id} expects UUID. If alias is passed, we might need a workaround.
    # For now, let's assume id_or_alias IS the ID unless we implement a search by alias.
    # Looking at secrets_agent/api/secrets.py, it only has GET /{secret_id}.
    return await proxy_request("GET", f"/v1/secrets/{id_or_alias}")


@router.patch("/{secret_id}")
async def update_portal_secret(
    secret_id: str,
    payload: PortalSecretUpdate,
    current_user: User = Depends(RequireRole(["admin", "operator"])),
) -> Any:
    """Update secret metadata."""
    return await proxy_request("PATCH", f"/v1/secrets/{secret_id}", json_data=payload.model_dump())


@router.post("/{secret_id}/rotate")
async def rotate_portal_secret(
    secret_id: str,
    payload: PortalSecretRotate,
    current_user: User = Depends(RequireRole(["admin", "operator"])),
) -> Any:
    """Rotate secret value."""
    return await proxy_request(
        "POST", f"/v1/secrets/{secret_id}/rotate", json_data=payload.model_dump()
    )


@router.delete("/{secret_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_portal_secret(
    secret_id: str,
    current_user: User = Depends(RequireRole(["admin"])),
) -> Response:
    """Delete secret."""
    await proxy_request("DELETE", f"/v1/secrets/{secret_id}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{secret_id}/reveal", response_model=PortalSecretRevealResponse)
async def reveal_portal_secret(
    secret_id: str,
    payload: PortalSecretRevealRequest,
    current_user: User = Depends(RequireRole(["admin", "BreakGlass"])),
) -> Any:
    """
    Break-glass reveal of a secret value.
    Requires password re-authentication and a reason.
    """
    # 1. Password re-auth
    if not verify_password(payload.password, current_user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid password")

    # 2. Proxy read request to secrets_agent
    # secrets_agent/v1/secrets/{id}/read expects SecretReadRequest(reason=...)
    resp_data = await proxy_request(
        "POST", f"/v1/secrets/{secret_id}/read", json_data={"reason": payload.reason}
    )

    # 3. Augment response with expires_in_seconds
    return PortalSecretRevealResponse(
        id=resp_data["id"],
        alias=resp_data["alias"],
        tenant_id=resp_data["tenant_id"],
        env=resp_data["env"],
        value=resp_data["value"],
        expires_in_seconds=120,
    )


@router.get("/audit", response_model=list[dict[str, Any]])
async def list_portal_secret_audit(
    service_id: str | None = Query(None),
    tenant_id: str | None = Query(None),
    env: str | None = Query(None),
    secret_alias: str | None = Query(None),
    action: str | None = Query(None),
    result: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(RequireRole(["admin", "BreakGlass"])),
) -> Any:
    """Query secret audit logs via secrets_agent proxy."""
    params = {
        "service_id": service_id,
        "tenant_id": tenant_id,
        "env": env,
        "secret_alias": secret_alias,
        "action": action,
        "result": result,
        "limit": limit,
        "offset": offset,
    }
    # Filter out None values
    params = {k: v for k, v in params.items() if v is not None}
    return await proxy_request("GET", "/v1/audit", params=params)
