"""
Vultr API v2 adapter for the Server Agent.
Implements the full ServerProviderAdapter interface.
Base URL: https://api.vultr.com/v2
Auth: Bearer token via vault secret_alias.
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import structlog

from apps.server_agent.adapters.base import (
    BackupMeta,
    BackupScheduleSpec,
    ConsoleAccess,
    CreateInstanceSpec,
    InstanceMeta,
    ServerProviderAdapter,
    SnapshotMeta,
)

logger = structlog.get_logger(__name__)


class VultrAdapter(ServerProviderAdapter):
    """Vultr API v2 implementation."""

    def __init__(self, api_key: str, base_url: str = "https://api.vultr.com") -> None:
        # api_key used only for auth header -- never logged or stored beyond this object
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=60,
        )

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        r = await self._client.request(method, path, **kwargs)
        if r.status_code >= 400:
            logger.error("vultr_api_error", status=r.status_code, path=path, body=r.text[:300])
            r.raise_for_status()
        if r.status_code == 204 or not r.content:
            return {}
        return r.json()

    def _parse_instance(self, raw: dict) -> InstanceMeta:
        return InstanceMeta(
            provider_instance_id=raw["id"],
            label=raw.get("label", ""),
            hostname=raw.get("hostname", ""),
            os=raw.get("os", ""),
            plan=raw.get("plan", ""),
            region=raw.get("region", ""),
            ip_v4=raw.get("main_ip", ""),
            ip_v6=raw.get("v6_main_ip", ""),
            status=raw.get("status", "pending"),
            power_status=raw.get("power_status", "off"),
            vcpu_count=raw.get("vcpu_count", 0),
            ram_mb=raw.get("ram", 0),
            disk_gb=raw.get("disk", 0),
            tags=raw.get("tags", {}),
        )

    # -- Instance lifecycle --

    async def list_instances(self) -> list[InstanceMeta]:
        data = await self._request("GET", "/v2/instances")
        return [self._parse_instance(i) for i in data.get("instances", [])]

    async def get_instance(self, provider_id: str) -> InstanceMeta:
        data = await self._request("GET", f"/v2/instances/{provider_id}")
        return self._parse_instance(data["instance"])

    async def create_instance(self, spec: CreateInstanceSpec) -> InstanceMeta:
        body = {
            "region": spec.region,
            "plan": spec.plan,
            "os_id": int(spec.os_id) if spec.os_id.isdigit() else spec.os_id,
            "label": spec.label,
            "hostname": spec.hostname,
            "sshkey_id": spec.ssh_keys if spec.ssh_keys else None,
            "tags": list(spec.tags.keys()) if spec.tags else [],
        }
        body = {k: v for k, v in body.items() if v is not None}
        data = await self._request("POST", "/v2/instances", json=body)
        return self._parse_instance(data["instance"])

    async def delete_instance(self, provider_id: str) -> None:
        await self._request("DELETE", f"/v2/instances/{provider_id}")

    async def rebuild_instance(self, provider_id: str, os_id: str) -> InstanceMeta:
        body = {"os_id": int(os_id) if os_id.isdigit() else os_id}
        await self._request("POST", f"/v2/instances/{provider_id}/reinstall", json=body)
        return await self.get_instance(provider_id)

    # -- Power actions --

    async def start(self, provider_id: str) -> None:
        await self._request("POST", f"/v2/instances/{provider_id}/start")

    async def stop(self, provider_id: str) -> None:
        await self._request("POST", f"/v2/instances/{provider_id}/halt")

    async def reboot(self, provider_id: str) -> None:
        await self._request("POST", f"/v2/instances/{provider_id}/reboot")

    # -- Console --

    async def get_console_url(self, provider_id: str) -> ConsoleAccess:
        data = await self._request("GET", f"/v2/instances/{provider_id}/vnc")
        return ConsoleAccess(
            url=data.get("vnc", {}).get("url", ""),
            type="vnc",
        )

    # -- Snapshots --

    async def list_snapshots(self, provider_id: str) -> list[SnapshotMeta]:
        data = await self._request("GET", "/v2/snapshots")
        # Vultr snapshots are global; filter by instance_id
        return [
            SnapshotMeta(
                provider_snapshot_id=s["id"],
                name=s.get("description", s["id"]),
                size_gb=s.get("size", 0) / (1024**3) if s.get("size") else None,
                status="complete" if s.get("status") == "complete" else "pending",
            )
            for s in data.get("snapshots", [])
            if s.get("instance_id") == provider_id or not provider_id
        ]

    async def create_snapshot(self, provider_id: str, name: str) -> SnapshotMeta:
        data = await self._request(
            "POST", "/v2/snapshots", json={"instance_id": provider_id, "description": name}
        )
        snap = data.get("snapshot", {})
        return SnapshotMeta(
            provider_snapshot_id=snap["id"],
            name=name,
            status="pending",
        )

    async def delete_snapshot(self, snapshot_id: str) -> None:
        await self._request("DELETE", f"/v2/snapshots/{snapshot_id}")

    async def restore_snapshot(self, provider_id: str, snapshot_id: str) -> None:
        await self._request(
            "POST",
            f"/v2/instances/{provider_id}/restore",
            json={"snapshot_id": snapshot_id},
        )

    # -- Backups --

    async def list_backups(self, provider_id: str) -> list[BackupMeta]:
        data = await self._request("GET", "/v2/backups", params={"instance_id": provider_id})
        return [
            BackupMeta(
                provider_backup_id=b["id"],
                backup_type="automatic",
                size_gb=b.get("size", 0) / (1024**3) if b.get("size") else None,
                status="complete" if b.get("status") == "complete" else "pending",
                created_at=datetime.fromisoformat(b["date_created"])
                if b.get("date_created")
                else None,
            )
            for b in data.get("backups", [])
        ]

    async def create_backup(self, provider_id: str) -> BackupMeta:
        # Vultr doesn't have on-demand backup; use snapshot instead
        snap = await self.create_snapshot(provider_id, f"backup-{provider_id}")
        return BackupMeta(
            provider_backup_id=snap.provider_snapshot_id,
            backup_type="manual",
            status="pending",
        )

    async def restore_backup(self, provider_id: str, backup_id: str) -> None:
        await self._request(
            "POST",
            f"/v2/instances/{provider_id}/restore",
            json={"backup_id": backup_id},
        )

    async def set_backup_schedule(self, provider_id: str, schedule: BackupScheduleSpec) -> None:
        body: dict = {"type": schedule.schedule_type, "hour": schedule.hour}
        if schedule.dow is not None:
            body["dow"] = schedule.dow
        if schedule.dom is not None:
            body["dom"] = schedule.dom
        await self._request("POST", f"/v2/instances/{provider_id}/backup-schedule", json=body)

    async def get_backup_schedule(self, provider_id: str) -> BackupScheduleSpec | None:
        try:
            data = await self._request("GET", f"/v2/instances/{provider_id}/backup-schedule")
            sched = data.get("backup_schedule", {})
            if not sched or not sched.get("type"):
                return None
            return BackupScheduleSpec(
                schedule_type=sched["type"],
                hour=sched.get("hour", 0),
                dow=sched.get("dow"),
                dom=sched.get("dom"),
            )
        except Exception:
            return None

    async def disable_backups(self, provider_id: str) -> None:
        await self._request("PATCH", f"/v2/instances/{provider_id}", json={"backups": "disabled"})

    # -- Metadata / Catalog --

    async def list_regions(self) -> list[dict]:
        data = await self._request("GET", "/v2/regions")
        return data.get("regions", [])

    async def list_plans(self) -> list[dict]:
        data = await self._request("GET", "/v2/plans")
        return data.get("plans", [])

    async def list_os_images(self) -> list[dict]:
        data = await self._request("GET", "/v2/os")
        return data.get("os", [])
