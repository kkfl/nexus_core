"""
Template engine with built-in library for common Nexus events.
Supports simple {variable} substitution.
"""
from __future__ import annotations

import re
from typing import Dict, Optional


# ---------------------------------------------------------------------------
# Built-in template library
# ---------------------------------------------------------------------------

BUILTIN_TEMPLATES: Dict[str, Dict[str, str]] = {
    "agent_down": {
        "subject": "🚨 Agent Down: {agent}",
        "body": "NEXUS ALERT — Agent Down\n\nAgent: {agent}\nReason: {reason}\nEnvironment: {env}\nTime: {timestamp}\n\nImmediate action required.",
    },
    "job_failed": {
        "subject": "⚠️ Job Failed: {job_id}",
        "body": "NEXUS ALERT — Job Failure\n\nService: {service}\nJob ID: {job_id}\nError: {error}\nEnvironment: {env}\nTime: {timestamp}",
    },
    "auth_denied": {
        "subject": "🔒 Auth Denied: {service_id}",
        "body": "NEXUS SECURITY ALERT — Authentication Denied\n\nService: {service_id}\nPath: {path}\nIP: {ip}\nTime: {timestamp}",
    },
    "high_latency": {
        "subject": "🐢 High Latency: {service}",
        "body": "NEXUS ALERT — High Latency Detected\n\nService: {service}\nP99 Latency: {p99_ms}ms\nThreshold: {threshold_ms}ms\nEnvironment: {env}\nTime: {timestamp}",
    },
    "dns_drift": {
        "subject": "🌐 DNS Drift Detected: {zone}",
        "body": "NEXUS ALERT — DNS Drift\n\nZone: {zone}\nRecord: {record}\nExpected: {expected}\nActual: {actual}\nTime: {timestamp}",
    },
    "generic": {
        "subject": "{subject}",
        "body": "{body}",
    },
}


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

def _substitute(template: str, context: Dict[str, str]) -> str:
    """Simple {key} substitution. Unknown keys are left as-is."""
    def replace(m):
        key = m.group(1)
        return str(context.get(key, m.group(0)))
    return re.sub(r'\{(\w+)\}', replace, template)


def render_template(
    template_id: str,
    context: Dict | None = None,
    *,
    subject_override: Optional[str] = None,
    body_override: Optional[str] = None,
    db_template_subject: Optional[str] = None,
    db_template_body: Optional[str] = None,
) -> tuple[Optional[str], str]:
    """
    Render subject + body for a notification.
    Priority: db template > builtin template > raw override.
    Returns (subject, body).
    """
    ctx = context or {}

    # Inject timestamp if not provided
    from datetime import datetime, timezone
    if "timestamp" not in ctx:
        ctx = {**ctx, "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")}

    if db_template_body:
        subject_tpl = db_template_subject or ""
        body_tpl = db_template_body
    elif template_id and template_id in BUILTIN_TEMPLATES:
        t = BUILTIN_TEMPLATES[template_id]
        subject_tpl = t.get("subject", "")
        body_tpl = t["body"]
    else:
        # Raw message passthrough
        subject_tpl = subject_override or ""
        body_tpl = body_override or ""

    subject = _substitute(subject_tpl, ctx) if subject_tpl else None
    body = _substitute(body_tpl, ctx)
    return subject, body
