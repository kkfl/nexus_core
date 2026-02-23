"""
PBX mutating operations (V1: core reload only).

core reload is:
- Safe: it re-reads config without dropping calls
- Idempotent: running it twice does not change system state
- AMI-executable: Action: Command / Command: core reload
"""
from typing import Any, Dict

from apps.pbx_agent.adapters.ami import run_ami_command
from apps.pbx_agent.config import config


async def reload_asterisk(host: str, port: int, username: str, secret: str) -> Dict[str, Any]:
    """
    Trigger a safe Asterisk configuration reload.
    Idempotent: can be run multiple times without side effects.
    """
    if config.pbx_mock:
        return {"reloaded": True, "output": "Reloading... (mock)", "mock": True}

    out = await run_ami_command(host, port, username, secret, "core reload")
    # Expected: "Reloading modules..." or similar
    success = "Reloading" in out or "reload" in out.lower() or len(out.strip()) > 0
    return {"reloaded": success, "output": out[:300]}
