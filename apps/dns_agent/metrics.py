"""Simple in-process metrics counters for the DNS Agent."""

from __future__ import annotations

from collections import defaultdict

_counters: dict[str, int] = defaultdict(int)
_latency_buckets: dict[str, list] = defaultdict(list)


def inc(name: str, by: int = 1) -> None:
    _counters[name] += by


def record_latency(name: str, ms: float) -> None:
    _latency_buckets[name].append(ms)
    if len(_latency_buckets[name]) > 1000:
        _latency_buckets[name] = _latency_buckets[name][-500:]


def metrics_text() -> str:
    lines = [f"dns_{k} {v}" for k, v in sorted(_counters.items())]
    for name, values in sorted(_latency_buckets.items()):
        if values:
            avg = sum(values) / len(values)
            lines.append(f"dns_{name}_avg_ms {round(avg, 2)}")
            lines.append(f"dns_{name}_count {len(values)}")
    return "\n".join(lines) + "\n"
