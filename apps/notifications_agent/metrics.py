"""
Simple in-process metrics counters for notifications_agent.
"""

from __future__ import annotations

from collections import defaultdict
from threading import Lock

_lock = Lock()
_counters: dict[str, int] = defaultdict(int)
_latency_ms: list[float] = []  # bounded list for p50/p99


def inc(name: str, amount: int = 1) -> None:
    with _lock:
        _counters[name] += amount


def record_latency(ms: float) -> None:
    with _lock:
        _latency_ms.append(ms)
        if len(_latency_ms) > 10000:
            _latency_ms.pop(0)


def snapshot() -> str:
    with _lock:
        lines = []
        for k, v in sorted(_counters.items()):
            lines.append(f"{k} {v}")
        if _latency_ms:
            sorted_ms = sorted(_latency_ms)
            n = len(sorted_ms)
            p50 = sorted_ms[int(n * 0.5)]
            p99 = sorted_ms[min(int(n * 0.99), n - 1)]
            lines.append(f"notification_latency_p50_ms {round(p50, 1)}")
            lines.append(f"notification_latency_p99_ms {round(p99, 1)}")
        return "\n".join(lines)
