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
