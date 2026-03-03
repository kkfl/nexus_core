"""
NexusEvent — versioned event envelope for the Nexus event bus.

All events published through the bus MUST use this envelope.
"""

from __future__ import annotations

import datetime
import json
import uuid
from typing import Any

from pydantic import BaseModel, Field


class EventActor(BaseModel):
    """Who or what triggered the event."""

    type: str = "service"  # "user" | "service" | "system"
    id: str = ""


class NexusEvent(BaseModel):
    """
    Canonical event envelope — v1.

    Serialised to Redis Streams as a flat dict of strings
    (streams require {field: bytes} entries).
    """

    # ── Identity ──────────────────────────────────────────────────────────
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str  # dotted namespace, e.g. "dns.zone.imported"
    event_version: int = 1

    # ── Timing ────────────────────────────────────────────────────────────
    occurred_at: str = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC).isoformat()
    )

    # ── Provenance ────────────────────────────────────────────────────────
    produced_by: str  # service ID, e.g. "dns-agent"
    correlation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    causation_id: str | None = None
    actor: EventActor = Field(default_factory=EventActor)
    tenant_id: str | None = None

    # ── Classification ────────────────────────────────────────────────────
    severity: str = "info"  # debug | info | warning | error | critical
    tags: list[str] = Field(default_factory=list)

    # ── Payload ───────────────────────────────────────────────────────────
    payload: dict[str, Any] = Field(default_factory=dict)
    payload_schema_version: int = 1
    idempotency_key: str | None = None

    # ── Security (placeholder) ────────────────────────────────────────────
    signature: str | None = None

    # ── Serialisation helpers ─────────────────────────────────────────────

    def to_stream_dict(self) -> dict[str, str]:
        """Flatten to {str: str} for XADD."""
        data = self.model_dump()
        # Nested objects → JSON strings
        data["actor"] = json.dumps(data["actor"])
        data["payload"] = json.dumps(data["payload"])
        data["tags"] = json.dumps(data["tags"])
        # None → empty string (Redis doesn't accept None)
        return {k: str(v) if v is not None else "" for k, v in data.items()}

    @classmethod
    def from_stream_dict(cls, raw: dict[bytes | str, bytes | str]) -> NexusEvent:
        """Parse a Redis Stream entry back into a NexusEvent."""
        decoded: dict[str, str] = {}
        for k, v in raw.items():
            key = k.decode() if isinstance(k, bytes) else k
            val = v.decode() if isinstance(v, bytes) else v
            decoded[key] = val

        # Restore nested JSON fields
        decoded["actor"] = json.loads(decoded.get("actor", "{}"))
        decoded["payload"] = json.loads(decoded.get("payload", "{}"))
        decoded["tags"] = json.loads(decoded.get("tags", "[]"))

        # Restore int fields
        for int_field in ("event_version", "payload_schema_version"):
            if int_field in decoded:
                decoded[int_field] = int(decoded[int_field])

        # Restore None for empty strings
        for key in ("causation_id", "idempotency_key", "signature", "tenant_id"):
            if decoded.get(key) == "" or decoded.get(key) == "None":
                decoded[key] = None

        return cls.model_validate(decoded)

    def stream_key(self) -> str:
        """Redis stream key for this event type."""
        return f"nexus:events:{self.event_type}"
