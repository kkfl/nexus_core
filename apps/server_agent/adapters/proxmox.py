"""
Proxmox VE API adapter for the Server Agent.
V1: list + get + power actions only.
Snapshot/backup methods are stubs gated by PROXMOX_ENABLE_SNAPSHOTS feature flag.
Auth: API tokens only (PVEAPIToken=user!tokenid=secret).
"""

from __future__ import annotations

import httpx
import structlog

from apps.server_agent.adapters.base import (
    BackupMeta,
    BackupScheduleSpec,
    ConsoleAccess,
    CreateInstanceSpec,
    InstanceMeta,
    InstanceResourceMeta,
    ServerProviderAdapter,
    SnapshotMeta,
)

logger = structlog.get_logger(__name__)

# Proxmox ostype codes → human-readable names
_OSTYPE_MAP = {
    "l26": "Linux",
    "l24": "Linux (2.4)",
    "win11": "Windows 11",
    "win10": "Windows 10",
    "win8": "Windows 8",
    "win7": "Windows 7",
    "w2k19": "Windows Server 2019",
    "w2k22": "Windows Server 2022",
    "w2k16": "Windows Server 2016",
    "w2k12": "Windows Server 2012",
    "w2k8": "Windows Server 2008",
    "solaris": "Solaris",
    "other": "Other",
    "wxp": "Windows XP",
    "wvista": "Windows Vista",
}


class ProxmoxAdapter(ServerProviderAdapter):
    """Proxmox VE API implementation (partial V1)."""

    def __init__(
        self,
        base_url: str,
        api_token: str,
        node: str = "pve",
        verify_ssl: bool = True,
    ) -> None:
        self._node = node
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"PVEAPIToken={api_token}"},
            verify=verify_ssl,
            timeout=60,
        )

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        r = await self._client.request(method, path, **kwargs)
        if r.status_code >= 400:
            logger.error("proxmox_api_error", status=r.status_code, path=path, body=r.text[:300])
            r.raise_for_status()
        data = r.json()
        return data.get("data", data)

    async def get_node_status(self) -> dict:
        """Fetch node-level resource stats (CPU, RAM, disk, uptime)."""
        data = await self._request("GET", f"/api2/json/nodes/{self._node}/status")
        if not isinstance(data, dict):
            return {}

        cpu_info = data.get("cpuinfo", {})
        mem = data.get("memory", {})
        rootfs = data.get("rootfs", {})

        cpu_total = cpu_info.get("cores", 0) * cpu_info.get("sockets", 1)
        cpu_usage_pct = round(data.get("cpu", 0) * 100, 1)

        ram_total = mem.get("total", 0)
        ram_used = mem.get("used", 0)
        ram_free = mem.get("free", 0)

        disk_total = rootfs.get("total", 0)
        disk_used = rootfs.get("used", 0)
        disk_free = rootfs.get("free", 0)

        # Fetch all storage pools (local-lvm, ZFS, NFS, etc.)
        storage_pools: list[dict] = []
        try:
            storage_data = await self._request("GET", f"/api2/json/nodes/{self._node}/storage")
            if isinstance(storage_data, list):
                for pool in storage_data:
                    if not pool.get("active"):
                        continue
                    s_total = pool.get("total", 0)
                    s_used = pool.get("used", 0)
                    s_avail = pool.get("avail", 0)
                    s_pct = round((s_used / s_total * 100) if s_total else 0, 1)
                    pool_entry = {
                        "name": pool.get("storage", "unknown"),
                        "type": pool.get("type", "unknown"),
                        "content": pool.get("content", ""),
                        "total_gb": round(s_total / (1024**3), 1),
                        "used_gb": round(s_used / (1024**3), 1),
                        "free_gb": round(s_avail / (1024**3), 1),
                        "usage_pct": s_pct,
                    }
                    # Skip dir-type pools whose total matches rootfs — they are
                    # the same physical partition (e.g. local, Mouhab share rootfs).
                    rootfs_total_gb = round(disk_total / (1024**3), 1)
                    if pool_entry["type"] == "dir" and pool_entry["total_gb"] == rootfs_total_gb:
                        continue
                    storage_pools.append(pool_entry)
        except Exception as e:
            logger.warning("storage_pools_fetch_failed", error=str(e))

        return {
            "node": self._node,
            "cpu_cores": cpu_total,
            "cpu_usage_pct": cpu_usage_pct,
            "ram_total_gb": round(ram_total / (1024**3), 1),
            "ram_used_gb": round(ram_used / (1024**3), 1),
            "ram_free_gb": round(ram_free / (1024**3), 1),
            "ram_usage_pct": round((ram_used / ram_total * 100) if ram_total else 0, 1),
            "disk_total_gb": round(disk_total / (1024**3), 1),
            "disk_used_gb": round(disk_used / (1024**3), 1),
            "disk_free_gb": round(disk_free / (1024**3), 1),
            "disk_usage_pct": round((disk_used / disk_total * 100) if disk_total else 0, 1),
            "storage_pools": storage_pools,
            "uptime_seconds": data.get("uptime", 0),
        }

    def _parse_instance(self, raw: dict, ip_v4: str = "", ip_v6: str = "") -> InstanceMeta:
        status = raw.get("status", "unknown")
        ostype = raw.get("ostype", "")
        os_label = _OSTYPE_MAP.get(ostype, ostype or "Unknown")
        return InstanceMeta(
            provider_instance_id=str(raw.get("vmid", "")),
            label=raw.get("name", ""),
            hostname=raw.get("name", ""),
            os=os_label,
            plan=f"{raw.get('cores', 0)}C/{raw.get('maxmem', 0) // (1024**3)}GB",
            region=self._node,
            status="running"
            if status == "running"
            else "stopped"
            if status == "stopped"
            else status,
            power_status="running" if status == "running" else "stopped",
            vcpu_count=raw.get("cores", raw.get("cpus", 0)),
            ram_mb=raw.get("maxmem", 0) // (1024**2),
            disk_gb=raw.get("maxdisk", 0) // (1024**3),
            ip_v4=ip_v4,
            ip_v6=ip_v6,
        )

    async def _get_vm_ips(self, vmid: str) -> tuple[str, str]:
        """Try to fetch IPs from QEMU guest agent. Returns (ipv4, ipv6)."""
        try:
            r = await self._client.request(
                "GET",
                f"/api2/json/nodes/{self._node}/qemu/{vmid}/agent/network-get-interfaces",
            )
            if r.status_code >= 400:
                return "", ""
            data = r.json().get("data", {})
            ip_v4, ip_v6 = "", ""
            if isinstance(data, dict):
                ifaces = data.get("result", [])
            elif isinstance(data, list):
                ifaces = data
            else:
                return "", ""
            for iface in ifaces:
                if iface.get("name") in ("lo", "lo0"):
                    continue
                for addr in iface.get("ip-addresses", []):
                    atype = addr.get("ip-address-type", "")
                    aip = addr.get("ip-address", "")
                    if atype == "ipv4" and not ip_v4 and not aip.startswith("127."):
                        ip_v4 = aip
                    elif atype == "ipv6" and not ip_v6 and not aip.startswith("fe80"):
                        ip_v6 = aip
            return ip_v4, ip_v6
        except Exception:
            return "", ""

    async def _get_vm_ostype(self, vmid: str) -> str:
        """Fetch ostype from VM config (list endpoint doesn't include it)."""
        try:
            data = await self._request("GET", f"/api2/json/nodes/{self._node}/qemu/{vmid}/config")
            ostype = data.get("ostype", "") if isinstance(data, dict) else ""
            return _OSTYPE_MAP.get(ostype, ostype or "Unknown")
        except Exception:
            return "Unknown"

    # -- Instance lifecycle --

    async def list_instances(self) -> list[InstanceMeta]:
        data = await self._request("GET", f"/api2/json/nodes/{self._node}/qemu")
        if not isinstance(data, list):
            return []
        instances = []
        for vm in data:
            vmid = str(vm.get("vmid", ""))
            ip_v4, ip_v6 = "", ""
            os_label = "Unknown"
            if vmid:
                os_label = await self._get_vm_ostype(vmid)
                # Only query agent for running VMs (stopped VMs won't respond)
                if vm.get("status") == "running":
                    ip_v4, ip_v6 = await self._get_vm_ips(vmid)
            # Inject ostype into raw dict for _parse_instance
            vm_with_os = {**vm, "ostype": os_label}
            instances.append(self._parse_instance(vm_with_os, ip_v4=ip_v4, ip_v6=ip_v6))
        return instances

    async def get_instance(self, provider_id: str) -> InstanceMeta:
        data = await self._request(
            "GET", f"/api2/json/nodes/{self._node}/qemu/{provider_id}/status/current"
        )
        return self._parse_instance(data)

    async def create_instance(self, spec: CreateInstanceSpec) -> InstanceMeta:
        # V1: basic create with clone or direct create
        body = {
            "vmid": "next",  # auto-assign
            "name": spec.hostname,
            "cores": 1,
            "memory": 1024,
            "ostype": spec.os_id,
        }
        await self._request("POST", f"/api2/json/nodes/{self._node}/qemu", data=body)
        # Get the newly created VM (simplified -- real impl would parse task UPID)
        vms = await self.list_instances()
        for vm in vms:
            if vm.label == spec.hostname:
                return vm
        raise RuntimeError(f"VM created but not found: {spec.hostname}")

    async def delete_instance(self, provider_id: str) -> None:
        await self._request("DELETE", f"/api2/json/nodes/{self._node}/qemu/{provider_id}")

    async def rebuild_instance(self, provider_id: str, os_id: str) -> InstanceMeta:
        raise NotImplementedError("Proxmox rebuild not supported in V1")

    # -- Power actions --

    async def start(self, provider_id: str) -> None:
        await self._request(
            "POST", f"/api2/json/nodes/{self._node}/qemu/{provider_id}/status/start"
        )

    async def stop(self, provider_id: str) -> None:
        await self._request("POST", f"/api2/json/nodes/{self._node}/qemu/{provider_id}/status/stop")

    async def reboot(self, provider_id: str) -> None:
        await self._request(
            "POST", f"/api2/json/nodes/{self._node}/qemu/{provider_id}/status/reboot"
        )

    # -- Console --

    async def get_console_url(self, provider_id: str) -> ConsoleAccess:
        # Proxmox noVNC page requires a PVEAuthCookie set on the Proxmox
        # domain, which we can't provide cross-origin.  Instead, deep-link
        # to the Proxmox web GUI console tab for this VM.  The user needs
        # to be logged into the Proxmox web UI in their browser.
        import urllib.parse

        base = str(self._client.base_url).rstrip("/")
        # Proxmox deep-link hash: #v1:0:=qemu/<vmid>:4::::::: opens the
        # Console tab for the QEMU VM directly.
        fragment = urllib.parse.quote(f"v1:0:=qemu/{provider_id}:4:::::::", safe="")
        url = f"{base}/#{fragment}"
        return ConsoleAccess(url=url, type="proxmox_ui")

    # -- Live resource monitoring --

    async def get_instance_resources(self, provider_id: str) -> InstanceResourceMeta:
        """Fetch live CPU/RAM/disk usage for a single QEMU VM."""
        data = await self._request(
            "GET", f"/api2/json/nodes/{self._node}/qemu/{provider_id}/status/current"
        )
        if not isinstance(data, dict):
            return InstanceResourceMeta(provider="proxmox")

        cpu_pct = round(data.get("cpu", 0) * 100, 1)
        cpus = data.get("cpus", data.get("cores", 0))

        mem_used = data.get("mem", 0)
        mem_total = data.get("maxmem", 0)
        mem_used_mb = mem_used // (1024**2) if mem_used else 0
        mem_total_mb = mem_total // (1024**2) if mem_total else 0
        mem_pct = round((mem_used / mem_total * 100) if mem_total else 0, 1)

        disk_total = data.get("maxdisk", 0)
        disk_total_gb = round(disk_total / (1024**3), 1) if disk_total else 0

        return InstanceResourceMeta(
            provider="proxmox",
            status=data.get("status", "unknown"),
            cpu_usage_pct=cpu_pct,
            cpu_cores=cpus,
            ram_used_mb=mem_used_mb,
            ram_total_mb=mem_total_mb,
            ram_usage_pct=mem_pct,
            disk_total_gb=disk_total_gb,
            uptime_seconds=data.get("uptime", 0),
        )

    # -- Snapshots (stubs -- gated by PROXMOX_ENABLE_SNAPSHOTS) --

    async def list_snapshots(self, provider_id: str) -> list[SnapshotMeta]:
        data = await self._request(
            "GET", f"/api2/json/nodes/{self._node}/qemu/{provider_id}/snapshot"
        )
        if isinstance(data, list):
            return [
                SnapshotMeta(
                    provider_snapshot_id=s.get("name", ""),
                    name=s.get("name", ""),
                    description=s.get("description", ""),
                    status="complete",
                )
                for s in data
                if s.get("name") != "current"
            ]
        return []

    async def create_snapshot(self, provider_id: str, name: str) -> SnapshotMeta:
        await self._request(
            "POST",
            f"/api2/json/nodes/{self._node}/qemu/{provider_id}/snapshot",
            data={"snapname": name, "description": f"Nexus snapshot: {name}"},
        )
        return SnapshotMeta(provider_snapshot_id=name, name=name, status="pending")

    async def delete_snapshot(self, snapshot_id: str) -> None:
        raise NotImplementedError("Proxmox delete_snapshot requires vmid -- use via job worker")

    async def restore_snapshot(self, provider_id: str, snapshot_id: str) -> None:
        await self._request(
            "POST",
            f"/api2/json/nodes/{self._node}/qemu/{provider_id}/snapshot/{snapshot_id}/rollback",
        )

    # -- Backups (stubs) --

    async def list_backups(self, provider_id: str) -> list[BackupMeta]:
        # V1 stub -- would query storage content with vmid filter
        return []

    async def create_backup(self, provider_id: str) -> BackupMeta:
        data = await self._request(
            "POST",
            f"/api2/json/nodes/{self._node}/vzdump",
            data={"vmid": provider_id, "mode": "snapshot", "compress": "zstd"},
        )
        return BackupMeta(
            provider_backup_id=str(data.get("data", "")),
            backup_type="manual",
            status="pending",
        )

    async def restore_backup(self, provider_id: str, backup_id: str) -> None:
        raise NotImplementedError("Proxmox backup restore not supported in V1")

    async def set_backup_schedule(self, provider_id: str, schedule: BackupScheduleSpec) -> None:
        raise NotImplementedError("Proxmox backup scheduling not supported in V1")

    async def get_backup_schedule(self, provider_id: str) -> BackupScheduleSpec | None:
        return None

    async def disable_backups(self, provider_id: str) -> None:
        raise NotImplementedError("Proxmox backup management not supported in V1")

    # -- Metadata --

    async def list_regions(self) -> list[dict]:
        data = await self._request("GET", "/api2/json/nodes")
        if isinstance(data, list):
            return [
                {"id": n.get("node", ""), "name": n.get("node", ""), "status": n.get("status", "")}
                for n in data
            ]
        return []

    async def list_plans(self) -> list[dict]:
        # Proxmox doesn't have plans; return predefined templates
        return [
            {"id": "small", "vcpu": 1, "ram_mb": 1024, "disk_gb": 20},
            {"id": "medium", "vcpu": 2, "ram_mb": 4096, "disk_gb": 50},
            {"id": "large", "vcpu": 4, "ram_mb": 8192, "disk_gb": 100},
        ]

    async def list_os_images(self) -> list[dict]:
        data = await self._request(
            "GET",
            f"/api2/json/nodes/{self._node}/storage/local/content",
            params={"content": "iso"},
        )
        if isinstance(data, list):
            return [{"id": iso.get("volid", ""), "name": iso.get("volid", "")} for iso in data]
        return []
