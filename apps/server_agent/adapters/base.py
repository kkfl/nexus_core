"""
Abstract base class for server provider adapters.
All providers implement this interface -- enables easy swap/extension.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class InstanceMeta:
    provider_instance_id: str
    label: str
    hostname: str = ""
    os: str = ""
    plan: str = ""
    region: str = ""
    ip_v4: str = ""
    ip_v6: str = ""
    status: str = "pending"
    power_status: str = "off"
    vcpu_count: int = 0
    ram_mb: int = 0
    disk_gb: int = 0
    tags: dict = field(default_factory=dict)


@dataclass
class CreateInstanceSpec:
    label: str
    hostname: str
    region: str
    plan: str
    os_id: str
    ssh_keys: list[str] = field(default_factory=list)
    tags: dict = field(default_factory=dict)


@dataclass
class SnapshotMeta:
    provider_snapshot_id: str
    name: str
    description: str = ""
    size_gb: float | None = None
    status: str = "pending"
    created_at: datetime | None = None


@dataclass
class BackupMeta:
    provider_backup_id: str
    backup_type: str = "manual"
    size_gb: float | None = None
    status: str = "pending"
    created_at: datetime | None = None


@dataclass
class BackupScheduleSpec:
    schedule_type: str  # daily|weekly|monthly
    hour: int = 0
    dow: int | None = None  # day of week (1-7) for weekly
    dom: int | None = None  # day of month (1-28) for monthly


@dataclass
class ConsoleAccess:
    url: str
    type: str  # vnc|novnc|webterm
    token: str | None = None
    expires_at: datetime | None = None


@dataclass
class InstanceResourceMeta:
    """Live resource usage for an individual server/VM."""

    provider: str
    status: str = "unknown"
    cpu_usage_pct: float | None = None      # Proxmox: live; Vultr: N/A
    cpu_cores: int = 0
    ram_used_mb: int = 0                     # Proxmox: live used; Vultr: allocated
    ram_total_mb: int = 0
    ram_usage_pct: float | None = None       # Proxmox only
    disk_total_gb: float = 0
    disk_used_gb: float | None = None        # Proxmox: allocated to VM
    disk_usage_pct: float | None = None
    bandwidth_in_gb: float | None = None     # Vultr only
    bandwidth_out_gb: float | None = None    # Vultr only
    uptime_seconds: int = 0

    # ── GPU metrics (nvidia-smi / ROCm) ──
    gpu_name: str | None = None              # e.g. "NVIDIA RTX 4090"
    gpu_usage_pct: float | None = None       # GPU core utilization %
    gpu_vram_used_mb: int | None = None      # VRAM in use
    gpu_vram_total_mb: int | None = None     # Total VRAM
    gpu_vram_usage_pct: float | None = None
    gpu_temp_c: float | None = None          # Temperature °C
    gpu_power_draw_w: float | None = None    # Power draw watts
    gpu_count: int | None = None             # Number of GPUs

    # ── LLM inference metrics ──
    llm_model_loaded: str | None = None      # e.g. "llama-3.1-70b"
    llm_requests_active: int | None = None   # Current concurrent requests
    llm_avg_latency_ms: float | None = None  # Avg inference latency
    llm_tokens_per_sec: float | None = None  # Throughput

    # ── Voice agent metrics ──
    voice_concurrent_calls: int | None = None
    voice_max_concurrent: int | None = None
    voice_avg_latency_ms: float | None = None  # Round-trip voice latency
    voice_total_calls_today: int | None = None


class ServerProviderAdapter(ABC):
    """
    Interface for server provider adapters.
    Credential fetching done during __init__ via vault_read(secret_alias).
    No tokens stored as plain class attributes visible in logs.
    """

    # -- Instance lifecycle --
    @abstractmethod
    async def list_instances(self) -> list[InstanceMeta]:
        """List all instances from the provider."""
        ...

    @abstractmethod
    async def get_instance(self, provider_id: str) -> InstanceMeta:
        """Get a single instance by provider ID."""
        ...

    @abstractmethod
    async def create_instance(self, spec: CreateInstanceSpec) -> InstanceMeta:
        """Create a new instance. Returns metadata including provider_instance_id."""
        ...

    @abstractmethod
    async def delete_instance(self, provider_id: str) -> None:
        """Permanently delete an instance."""
        ...

    @abstractmethod
    async def rebuild_instance(self, provider_id: str, os_id: str) -> InstanceMeta:
        """Rebuild an instance with a new OS image."""
        ...

    # -- Power actions --
    @abstractmethod
    async def start(self, provider_id: str) -> None:
        """Power on an instance."""
        ...

    @abstractmethod
    async def stop(self, provider_id: str) -> None:
        """Power off an instance."""
        ...

    @abstractmethod
    async def reboot(self, provider_id: str) -> None:
        """Reboot an instance."""
        ...

    # -- Console access --
    @abstractmethod
    async def get_console_url(self, provider_id: str) -> ConsoleAccess:
        """Get console access URL/token for an instance."""
        ...

    # -- Live resource monitoring --
    @abstractmethod
    async def get_instance_resources(self, provider_id: str) -> InstanceResourceMeta:
        """Get live resource usage for a single instance."""
        ...

    # -- Snapshots --
    @abstractmethod
    async def list_snapshots(self, provider_id: str) -> list[SnapshotMeta]:
        """List snapshots for an instance."""
        ...

    @abstractmethod
    async def create_snapshot(self, provider_id: str, name: str) -> SnapshotMeta:
        """Create a snapshot. Returns metadata including provider_snapshot_id."""
        ...

    @abstractmethod
    async def delete_snapshot(self, snapshot_id: str) -> None:
        """Delete a snapshot by provider snapshot ID."""
        ...

    @abstractmethod
    async def restore_snapshot(self, provider_id: str, snapshot_id: str) -> None:
        """Restore an instance from a snapshot."""
        ...

    # -- Backups --
    @abstractmethod
    async def list_backups(self, provider_id: str) -> list[BackupMeta]:
        """List backups for an instance."""
        ...

    @abstractmethod
    async def create_backup(self, provider_id: str) -> BackupMeta:
        """Trigger a manual backup."""
        ...

    @abstractmethod
    async def restore_backup(self, provider_id: str, backup_id: str) -> None:
        """Restore an instance from a backup."""
        ...

    @abstractmethod
    async def set_backup_schedule(self, provider_id: str, schedule: BackupScheduleSpec) -> None:
        """Set or update the automatic backup schedule."""
        ...

    @abstractmethod
    async def get_backup_schedule(self, provider_id: str) -> BackupScheduleSpec | None:
        """Get the current backup schedule. Returns None if not configured."""
        ...

    @abstractmethod
    async def disable_backups(self, provider_id: str) -> None:
        """Disable automatic backups."""
        ...

    # -- Metadata / Catalog --
    @abstractmethod
    async def list_regions(self) -> list[dict]:
        """List available regions or nodes."""
        ...

    @abstractmethod
    async def list_plans(self) -> list[dict]:
        """List available plans/sizes."""
        ...

    @abstractmethod
    async def list_os_images(self) -> list[dict]:
        """List available OS images."""
        ...
