"""
Nexus Event Bus — shared event schema, transport, and developer API.

Usage (producer):
    from packages.shared.events import emit_event

    await emit_event(
        event_type="dns.zone.imported",
        payload={"zone_name": "example.com", "provider": "cloudflare"},
        produced_by="dns-agent",
        tenant_id="nexus",
    )

Usage (consumer):
    from packages.shared.events import EventBus

    bus = EventBus.from_url(redis_url)
    await bus.subscribe(
        event_types=["dns.zone.*"],
        group="automation-agent",
        handler=my_handler,
    )
"""

from packages.shared.events.api import emit_event
from packages.shared.events.schema import NexusEvent
from packages.shared.events.transport import EventBus

__all__ = ["NexusEvent", "EventBus", "emit_event"]
