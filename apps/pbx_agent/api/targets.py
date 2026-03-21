"""
Target management API — GET/POST/PATCH /v1/targets
"""

import json
import re

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from apps.pbx_agent.adapters import ami
from apps.pbx_agent.adapters.ssh_system import check_ssh_connectivity, collect_node_snapshot, sanitize_ssh_key
from apps.pbx_agent.audit.log import write_audit_event
from apps.pbx_agent.auth.identity import ServiceIdentity, get_service_identity
from apps.pbx_agent.client.secrets import SecretsError, delete_secret_by_alias, fetch_secret, store_secret
from apps.pbx_agent.schemas import (
    PbxTargetCreate, PbxTargetEdit, PbxTargetOut, PbxTargetRegister, PbxTargetUpdate,
    PbxRegistrationResult, VerifyCheckResult,
)
from apps.pbx_agent.store import postgres
from apps.pbx_agent.store.database import get_db

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/targets", tags=["targets"])


def _make_alias(name: str, suffix: str) -> str:
    """Generate a vault alias from PBX name, e.g. 'PBX-DC1' -> 'pbx.pbx-dc1.ami.secret'."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"pbx.{slug}.{suffix}"


@router.post("", response_model=PbxTargetOut, status_code=201)
async def create_target(
    payload: PbxTargetCreate,
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(get_db),
):
    if identity.read_only:
        raise HTTPException(status_code=403, detail="Read-only service cannot create targets")
    target = await postgres.create_target(db, payload)
    await write_audit_event(
        db,
        identity.correlation_id,
        identity.service_id,
        "create_target",
        "success",
        tenant_id=payload.tenant_id,
        env=payload.env,
        target_id=target.id,
    )
    await db.commit()
    await db.refresh(target)
    return PbxTargetOut.model_validate(target)


@router.get("", response_model=list[PbxTargetOut])
async def list_targets(
    tenant_id: str = Query(...),
    env: str = Query("prod"),
    limit: int = Query(100, le=500),
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(get_db),
):
    items = await postgres.list_targets(db, tenant_id=tenant_id, env=env, limit=limit)
    return [PbxTargetOut.model_validate(t) for t in items]


# ─── Register + Verify ────────────────────────────────────────────────────────


@router.post("/register", response_model=PbxRegistrationResult)
async def register_and_verify(
    payload: PbxTargetRegister,
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(get_db),
):
    """
    All-in-one PBX registration:
    1. Store raw credentials in the vault (AMI secret, SSH key, SSH password)
    2. Create the PBX target record with generated vault aliases
    3. Verify SSH connectivity (key and/or password)
    4. Verify AMI connectivity
    Returns per-check pass/fail results.
    """
    if identity.read_only:
        raise HTTPException(status_code=403, detail="Read-only service cannot register targets")

    checks: list[VerifyCheckResult] = []
    ami_alias = _make_alias(payload.name, "ami.secret")
    ssh_key_alias = _make_alias(payload.name, "ssh.key") if payload.ssh_key_pem else None
    ssh_pass_alias = _make_alias(payload.name, "ssh.password") if payload.ssh_password else None

    # ── Step 1: Store credentials in vault ──────────────────────────────
    try:
        await store_secret(
            alias=ami_alias, value=payload.ami_secret,
            tenant_id=payload.tenant_id, env=payload.env,
            description=f"AMI secret for {payload.name}",
            correlation_id=identity.correlation_id,
        )
        checks.append(VerifyCheckResult(check="Vault: AMI secret stored", passed=True))
    except SecretsError as e:
        checks.append(VerifyCheckResult(check="Vault: AMI secret stored", passed=False, detail=str(e)))
        return PbxRegistrationResult(
            target_name=payload.name, registered=False, checks=checks,
            error="Failed to store AMI secret in vault",
        )

    if payload.ssh_key_pem:
        try:
            await store_secret(
                alias=ssh_key_alias, value=sanitize_ssh_key(payload.ssh_key_pem),
                tenant_id=payload.tenant_id, env=payload.env,
                description=f"SSH private key for {payload.name}",
                correlation_id=identity.correlation_id,
            )
            checks.append(VerifyCheckResult(check="Vault: SSH key stored", passed=True))
        except SecretsError as e:
            checks.append(VerifyCheckResult(check="Vault: SSH key stored", passed=False, detail=str(e)))

    if payload.ssh_password:
        try:
            await store_secret(
                alias=ssh_pass_alias, value=payload.ssh_password,
                tenant_id=payload.tenant_id, env=payload.env,
                description=f"SSH password for {payload.name}",
                correlation_id=identity.correlation_id,
            )
            checks.append(VerifyCheckResult(check="Vault: SSH password stored", passed=True))
        except SecretsError as e:
            checks.append(VerifyCheckResult(check="Vault: SSH password stored", passed=False, detail=str(e)))

    # ── Step 2: Create PBX target record ────────────────────────────────
    try:
        create_payload = PbxTargetCreate(
            name=payload.name,
            tenant_id=payload.tenant_id,
            env=payload.env,
            host=payload.host,
            ami_port=payload.ami_port,
            ami_username=payload.ami_username,
            ami_secret_alias=ami_alias,
            ssh_port=payload.ssh_port,
            ssh_username=payload.ssh_username,
            ssh_key_alias=ssh_key_alias,
            ssh_password_alias=ssh_pass_alias,
        )
        target = await postgres.create_target(db, create_payload)
        await write_audit_event(
            db, identity.correlation_id, identity.service_id,
            "register_target", "success",
            tenant_id=payload.tenant_id, env=payload.env, target_id=target.id,
        )
        await db.commit()
        await db.refresh(target)
    except Exception as e:
        logger.error("register_target_db_error", error=str(e)[:200])
        return PbxRegistrationResult(
            target_name=payload.name, registered=False, checks=checks,
            error=f"Failed to create target record: {str(e)[:200]}",
        )

    # ── Step 3: Verify SSH connectivity ─────────────────────────────────
    # First check if SSH port is reachable at all
    ssh_reachable = await check_ssh_connectivity(payload.host, payload.ssh_port)
    if not ssh_reachable:
        checks.append(VerifyCheckResult(
            check="SSH: Port reachable", passed=False,
            detail=f"Cannot reach {payload.host}:{payload.ssh_port}",
        ))
    else:
        checks.append(VerifyCheckResult(check="SSH: Port reachable", passed=True))

        # Test SSH key auth
        if payload.ssh_key_pem:
            try:
                snap = await collect_node_snapshot(
                    host=payload.host, port=payload.ssh_port,
                    username=payload.ssh_username,
                    private_key_pem=payload.ssh_key_pem,
                )
                if snap.ssh_ok:
                    checks.append(VerifyCheckResult(check="SSH: Key authentication", passed=True))
                else:
                    checks.append(VerifyCheckResult(
                        check="SSH: Key authentication", passed=False,
                        detail=snap.error or "Key rejected",
                    ))
            except Exception as e:
                checks.append(VerifyCheckResult(
                    check="SSH: Key authentication", passed=False, detail=str(e)[:200],
                ))

        # Test SSH password auth
        if payload.ssh_password:
            try:
                snap = await collect_node_snapshot(
                    host=payload.host, port=payload.ssh_port,
                    username=payload.ssh_username,
                    password=payload.ssh_password,
                )
                if snap.ssh_ok:
                    checks.append(VerifyCheckResult(check="SSH: Password authentication", passed=True))
                else:
                    checks.append(VerifyCheckResult(
                        check="SSH: Password authentication", passed=False,
                        detail=snap.error or "Password rejected",
                    ))
            except Exception as e:
                checks.append(VerifyCheckResult(
                    check="SSH: Password authentication", passed=False, detail=str(e)[:200],
                ))

    # ── Step 4: Verify AMI connectivity ─────────────────────────────────
    ami_reachable = await ami.check_connectivity(payload.host, payload.ami_port)
    if not ami_reachable:
        checks.append(VerifyCheckResult(
            check="AMI: Port reachable", passed=False,
            detail=f"Cannot reach {payload.host}:{payload.ami_port}",
        ))
    else:
        checks.append(VerifyCheckResult(check="AMI: Port reachable", passed=True))

        # Step 4a: Test AMI login (auth only, no command)
        login_ok = await ami.check_ami_login(
            host=payload.host, port=payload.ami_port,
            username=payload.ami_username, secret=payload.ami_secret,
        )
        checks.append(VerifyCheckResult(
            check="AMI: Login successful", passed=login_ok,
            detail=None if login_ok else "Authentication failed — check AMI username/secret",
        ))

        # Step 4b: Test AMI command (only if login passed)
        if login_ok:
            try:
                version_str = await ami.run_ami_command(
                    host=payload.host, port=payload.ami_port,
                    username=payload.ami_username, secret=payload.ami_secret,
                    command="core show version",
                )
                checks.append(VerifyCheckResult(
                    check="AMI: Command response", passed=True,
                    detail=(version_str or "OK")[:100],
                ))
            except Exception as e:
                checks.append(VerifyCheckResult(
                    check="AMI: Command response", passed=False,
                    detail=f"{str(e)[:150]} (login works — command timed out, may be normal over WAN)",
                ))

    # Telegram notification
    try:
        from apps.notifications_agent.client.notifications_client import NotificationsClient
        import os
        nc = NotificationsClient(
            base_url=os.getenv("NOTIFICATIONS_BASE_URL", "http://notifications-agent:8008"),
            service_id="pbx-agent",
            api_key=os.getenv("NEXUS_NOTIF_AGENT_KEY", "nexus-notif-key-change-me"),
        )
        passed = sum(1 for c in checks if c.passed)
        await nc.notify(
            tenant_id=payload.tenant_id, env=payload.env, severity="info",
            channels=["telegram"],
            subject="\U0001f4de PBX Registered",
            body=f"{payload.name} ({payload.host}) — {passed}/{len(checks)} checks passed",
            idempotency_key=f"pbx-register:{target.id}",
        )
    except Exception:
        logger.warning("telegram_notify_failed", action="pbx_register")

    return PbxRegistrationResult(
        target_id=target.id,
        target_name=payload.name,
        registered=True,
        checks=checks,
    )


# ─── Verify existing target ──────────────────────────────────────────────────


@router.post("/{target_id}/verify", response_model=PbxRegistrationResult)
async def verify_target(
    target_id: str,
    tenant_id: str = Query("acme"),
    env: str = Query("prod"),
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(get_db),
):
    """
    Re-verify an already-registered PBX target:
    1. Fetch the target from DB
    2. Pull stored credentials from vault
    3. Run SSH + AMI connectivity checks
    Returns per-check pass/fail results.
    """
    target = await postgres.get_target(db, target_id, tenant_id, env)
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")

    checks: list[VerifyCheckResult] = []

    # ── Fetch credentials from vault ────────────────────────────────────
    ami_secret = None
    ssh_key_pem = None
    ssh_password = None

    try:
        ami_secret = await fetch_secret(
            alias=target.ami_secret_alias, tenant_id=tenant_id, env=env,
            reason="verify", correlation_id=identity.correlation_id,
        )
        checks.append(VerifyCheckResult(check="Vault: AMI secret readable", passed=True))
    except SecretsError as e:
        checks.append(VerifyCheckResult(check="Vault: AMI secret readable", passed=False, detail=str(e)))

    if target.ssh_key_alias:
        try:
            ssh_key_pem = await fetch_secret(
                alias=target.ssh_key_alias, tenant_id=tenant_id, env=env,
                reason="verify", correlation_id=identity.correlation_id,
            )
            checks.append(VerifyCheckResult(check="Vault: SSH key readable", passed=True))
        except SecretsError as e:
            checks.append(VerifyCheckResult(check="Vault: SSH key readable", passed=False, detail=str(e)))

    if target.ssh_password_alias:
        try:
            ssh_password = await fetch_secret(
                alias=target.ssh_password_alias, tenant_id=tenant_id, env=env,
                reason="verify", correlation_id=identity.correlation_id,
            )
            checks.append(VerifyCheckResult(check="Vault: SSH password readable", passed=True))
        except SecretsError as e:
            checks.append(VerifyCheckResult(check="Vault: SSH password readable", passed=False, detail=str(e)))

    # ── SSH checks ──────────────────────────────────────────────────────
    ssh_reachable = await check_ssh_connectivity(target.host, target.ssh_port)
    if not ssh_reachable:
        checks.append(VerifyCheckResult(
            check="SSH: Port reachable", passed=False,
            detail=f"Cannot reach {target.host}:{target.ssh_port}",
        ))
    else:
        checks.append(VerifyCheckResult(check="SSH: Port reachable", passed=True))

        if ssh_key_pem:
            try:
                snap = await collect_node_snapshot(
                    host=target.host, port=target.ssh_port,
                    username=target.ssh_username, private_key_pem=ssh_key_pem,
                )
                checks.append(VerifyCheckResult(
                    check="SSH: Key authentication",
                    passed=snap.ssh_ok,
                    detail=snap.error if not snap.ssh_ok else None,
                ))
            except Exception as e:
                checks.append(VerifyCheckResult(
                    check="SSH: Key authentication", passed=False, detail=str(e)[:200],
                ))

        if ssh_password:
            try:
                snap = await collect_node_snapshot(
                    host=target.host, port=target.ssh_port,
                    username=target.ssh_username, password=ssh_password,
                )
                checks.append(VerifyCheckResult(
                    check="SSH: Password authentication",
                    passed=snap.ssh_ok,
                    detail=snap.error if not snap.ssh_ok else None,
                ))
            except Exception as e:
                checks.append(VerifyCheckResult(
                    check="SSH: Password authentication", passed=False, detail=str(e)[:200],
                ))

    # ── AMI checks ──────────────────────────────────────────────────────
    ami_reachable = await ami.check_connectivity(target.host, target.ami_port)
    if not ami_reachable:
        checks.append(VerifyCheckResult(
            check="AMI: Port reachable", passed=False,
            detail=f"Cannot reach {target.host}:{target.ami_port}",
        ))
    else:
        checks.append(VerifyCheckResult(check="AMI: Port reachable", passed=True))
        if ami_secret:
            # Step: Test AMI login (auth only)
            login_ok = await ami.check_ami_login(
                host=target.host, port=target.ami_port,
                username=target.ami_username, secret=ami_secret,
            )
            checks.append(VerifyCheckResult(
                check="AMI: Login successful", passed=login_ok,
                detail=None if login_ok else "Authentication failed — check AMI username/secret",
            ))

            # Step: Test AMI command (only if login passed)
            if login_ok:
                try:
                    version_str = await ami.run_ami_command(
                        host=target.host, port=target.ami_port,
                        username=target.ami_username, secret=ami_secret,
                        command="core show version",
                    )
                    checks.append(VerifyCheckResult(
                        check="AMI: Command response", passed=True,
                        detail=(version_str or "OK")[:100],
                    ))
                except Exception as e:
                    checks.append(VerifyCheckResult(
                        check="AMI: Command response", passed=False,
                        detail=f"{str(e)[:150]} (login works — command timed out, may be normal over WAN)",
                    ))

    return PbxRegistrationResult(
        target_id=target.id,
        target_name=target.name,
        registered=True,
        checks=checks,
    )


# ─── Streaming verify (SSE) ───────────────────────────────────────────────────


@router.post("/{target_id}/verify-stream")
async def verify_target_stream(
    target_id: str,
    tenant_id: str = Query("acme"),
    env: str = Query("prod"),
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(get_db),
):
    """
    SSE-streaming verify: yields each check result as an event in real-time.
    The frontend opens the modal immediately and adds checks as they arrive.
    """
    target = await postgres.get_target(db, target_id, tenant_id, env)
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")

    async def _generate():
        def _evt(check: str, passed: bool, detail: str | None = None) -> str:
            data = json.dumps({"check": check, "passed": passed, "detail": detail})
            return f"event: check\ndata: {data}\n\n"

        # ── Vault reads ─────────────────────────────────────────────────
        ami_secret = None
        ssh_key_pem = None
        ssh_password = None

        try:
            ami_secret = await fetch_secret(
                alias=target.ami_secret_alias, tenant_id=tenant_id, env=env,
                reason="verify", correlation_id=identity.correlation_id,
            )
            yield _evt("Vault: AMI secret readable", True)
        except SecretsError as e:
            yield _evt("Vault: AMI secret readable", False, str(e))

        if target.ssh_key_alias:
            try:
                ssh_key_pem = await fetch_secret(
                    alias=target.ssh_key_alias, tenant_id=tenant_id, env=env,
                    reason="verify", correlation_id=identity.correlation_id,
                )
                yield _evt("Vault: SSH key readable", True)
            except SecretsError as e:
                yield _evt("Vault: SSH key readable", False, str(e))

        if target.ssh_password_alias:
            try:
                ssh_password = await fetch_secret(
                    alias=target.ssh_password_alias, tenant_id=tenant_id, env=env,
                    reason="verify", correlation_id=identity.correlation_id,
                )
                yield _evt("Vault: SSH password readable", True)
            except SecretsError as e:
                yield _evt("Vault: SSH password readable", False, str(e))

        # ── SSH checks ──────────────────────────────────────────────────
        ssh_reachable = await check_ssh_connectivity(target.host, target.ssh_port)
        if not ssh_reachable:
            yield _evt("SSH: Port reachable", False, f"Cannot reach {target.host}:{target.ssh_port}")
        else:
            yield _evt("SSH: Port reachable", True)

            if ssh_key_pem:
                try:
                    snap = await collect_node_snapshot(
                        host=target.host, port=target.ssh_port,
                        username=target.ssh_username, private_key_pem=ssh_key_pem,
                    )
                    yield _evt("SSH: Key authentication", snap.ssh_ok,
                               snap.error if not snap.ssh_ok else None)
                except Exception as e:
                    yield _evt("SSH: Key authentication", False, str(e)[:200])

            if ssh_password:
                try:
                    snap = await collect_node_snapshot(
                        host=target.host, port=target.ssh_port,
                        username=target.ssh_username, password=ssh_password,
                    )
                    yield _evt("SSH: Password authentication", snap.ssh_ok,
                               snap.error if not snap.ssh_ok else None)
                except Exception as e:
                    yield _evt("SSH: Password authentication", False, str(e)[:200])

        # ── AMI checks ──────────────────────────────────────────────────
        ami_reachable = await ami.check_connectivity(target.host, target.ami_port)
        if not ami_reachable:
            yield _evt("AMI: Port reachable", False, f"Cannot reach {target.host}:{target.ami_port}")
        else:
            yield _evt("AMI: Port reachable", True)
            if ami_secret:
                login_ok = await ami.check_ami_login(
                    host=target.host, port=target.ami_port,
                    username=target.ami_username, secret=ami_secret,
                )
                yield _evt("AMI: Login", login_ok,
                           None if login_ok else "Authentication failed — check AMI username/secret")

                if login_ok:
                    try:
                        version_str = await ami.run_ami_command(
                            host=target.host, port=target.ami_port,
                            username=target.ami_username, secret=ami_secret,
                            command="core show version",
                        )
                        yield _evt("AMI: Command response", True, (version_str or "OK")[:100])
                    except Exception as e:
                        yield _evt("AMI: Command response", False,
                                   f"{str(e)[:150]} (login works — may be normal over WAN)")

        # Signal completion
        done = json.dumps({"target_name": target.name, "target_id": target.id})
        yield f"event: done\ndata: {done}\n\n"

    return StreamingResponse(_generate(), media_type="text/event-stream")


# ─── Edit existing target (config + optional re-store credentials) ────────────


@router.put("/{target_id}/edit", response_model=PbxTargetOut)
async def edit_target(
    target_id: str,
    payload: PbxTargetEdit,
    tenant_id: str = Query("acme"),
    env: str = Query("prod"),
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(get_db),
):
    """
    Update a PBX target's config and optionally re-store credentials in vault.
    Only fields that are provided (non-None) are updated.
    """
    if identity.read_only:
        raise HTTPException(status_code=403, detail="Read-only service cannot edit targets")

    target = await postgres.get_target(db, target_id, tenant_id, env)
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")

    # Build update dict for config fields (non-credential)
    config_updates: dict = {}
    for field in ['name', 'host', 'ami_port', 'ami_username', 'ssh_port', 'ssh_username']:
        val = getattr(payload, field, None)
        if val is not None:
            config_updates[field] = val

    target_name = payload.name or target.name

    # Re-store credentials in vault if provided
    if payload.ami_secret:
        alias = _make_alias(target_name, "ami.secret")
        try:
            await store_secret(
                alias=alias, value=payload.ami_secret,
                tenant_id=tenant_id, env=env,
                description=f"AMI secret for {target_name}",
                correlation_id=identity.correlation_id,
            )
            config_updates['ami_secret_alias'] = alias
        except SecretsError as e:
            logger.warning("edit_store_ami_secret_error", error=str(e)[:200])

    if payload.ssh_key_pem:
        alias = _make_alias(target_name, "ssh.key")
        try:
            await store_secret(
                alias=alias, value=sanitize_ssh_key(payload.ssh_key_pem),
                tenant_id=tenant_id, env=env,
                description=f"SSH key for {target_name}",
                correlation_id=identity.correlation_id,
            )
            config_updates['ssh_key_alias'] = alias
        except SecretsError as e:
            logger.warning("edit_store_ssh_key_error", error=str(e)[:200])

    if payload.ssh_password:
        alias = _make_alias(target_name, "ssh.password")
        try:
            await store_secret(
                alias=alias, value=payload.ssh_password,
                tenant_id=tenant_id, env=env,
                description=f"SSH password for {target_name}",
                correlation_id=identity.correlation_id,
            )
            config_updates['ssh_password_alias'] = alias
        except SecretsError as e:
            logger.warning("edit_store_ssh_password_error", error=str(e)[:200])

    # Apply updates
    if config_updates:
        update_payload = PbxTargetUpdate(**config_updates)
        target = await postgres.update_target(db, target_id, tenant_id, env, update_payload)
        await write_audit_event(
            db, identity.correlation_id, identity.service_id,
            "edit_target", "success",
            tenant_id=tenant_id, env=env, target_id=target_id,
        )
        await db.commit()
        await db.refresh(target)

    return PbxTargetOut.model_validate(target)


# ─── CRUD by ID (must come after /register, /verify, and /edit) ───────────────



@router.get("/{target_id}", response_model=PbxTargetOut)
async def get_target(
    target_id: str,
    tenant_id: str = Query(...),
    env: str = Query("prod"),
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(get_db),
):
    target = await postgres.get_target(db, target_id, tenant_id, env)
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")
    return PbxTargetOut.model_validate(target)


@router.patch("/{target_id}", response_model=PbxTargetOut)
async def update_target(
    target_id: str,
    payload: PbxTargetUpdate,
    tenant_id: str = Query(...),
    env: str = Query("prod"),
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(get_db),
):
    if identity.read_only:
        raise HTTPException(status_code=403, detail="Read-only service cannot update targets")
    target = await postgres.update_target(db, target_id, tenant_id, env, payload)
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")
    await write_audit_event(
        db,
        identity.correlation_id,
        identity.service_id,
        "update_target",
        "success",
        tenant_id=tenant_id,
        env=env,
        target_id=target_id,
    )
    await db.commit()
    await db.refresh(target)
    return PbxTargetOut.model_validate(target)


@router.delete("/{target_id}", status_code=204)
async def delete_target(
    target_id: str,
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(get_db),
):
    """Remove a PBX target from the fleet and clean up associated secrets."""
    if identity.read_only:
        raise HTTPException(status_code=403, detail="Read-only service cannot delete targets")

    # Fetch target by ID only (UUIDs are globally unique)
    target = await postgres.get_target_by_id(db, target_id)
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")

    tenant_id = target.tenant_id
    env = target.env

    # Clean up associated secrets from vault (best-effort, non-blocking)
    aliases_to_delete = [
        a for a in [target.ami_secret_alias, target.ssh_key_alias, target.ssh_password_alias]
        if a
    ]
    deleted_secrets = 0
    for alias in aliases_to_delete:
        ok = await delete_secret_by_alias(
            alias=alias, tenant_id=tenant_id, env=env,
            correlation_id=identity.correlation_id,
        )
        if ok:
            deleted_secrets += 1
            logger.info("secret_cleaned_up", alias=alias)

    # Delete the target record
    await db.delete(target)
    await db.flush()
    await write_audit_event(
        db,
        identity.correlation_id,
        identity.service_id,
        "delete_target",
        "success",
        tenant_id=tenant_id,
        env=env,
        target_id=target_id,
        detail=f"Cleaned up {deleted_secrets}/{len(aliases_to_delete)} secrets",
    )
    await db.commit()

    # Telegram notification
    try:
        from apps.notifications_agent.client.notifications_client import NotificationsClient
        import os
        nc = NotificationsClient(
            base_url=os.getenv("NOTIFICATIONS_BASE_URL", "http://notifications-agent:8008"),
            service_id="pbx-agent",
            api_key=os.getenv("NEXUS_NOTIF_AGENT_KEY", "nexus-notif-key-change-me"),
        )
        await nc.notify(
            tenant_id=tenant_id, env=env, severity="info",
            channels=["telegram"],
            subject="\U0001f5d1\ufe0f PBX Deleted",
            body=f"{target.name} ({target.host})",
            idempotency_key=f"pbx-delete:{target_id}",
        )
    except Exception:
        logger.warning("telegram_notify_failed", action="pbx_delete")
