import time
from functools import wraps


class MetricsState:
    def __init__(self):
        self.counters: dict[str, float] = {}
        self.gauges: dict[str, float] = {}
        self.histograms: dict[str, list] = {}

    def inc(self, name: str, value: float = 1.0, **labels):
        key = self._make_key(name, labels)
        self.counters[key] = self.counters.get(key, 0) + value

    def set_gauge(self, name: str, value: float, **labels):
        key = self._make_key(name, labels)
        self.gauges[key] = value

    def observe(self, name: str, value: float, **labels):
        key = self._make_key(name, labels)
        if key not in self.histograms:
            self.histograms[key] = []
        self.histograms[key].append(value)
        # Keep bounded
        if len(self.histograms[key]) > 1000:
            self.histograms[key].pop(0)

    def _make_key(self, name: str, labels: dict) -> str:
        if not labels:
            return name
        lbls = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
        return f"{name}{{{lbls}}}"

    def render_prometheus(self) -> str:
        lines = []
        for k, v in self.counters.items():
            lines.append(f"{k} {v}")
        for k, v in self.gauges.items():
            lines.append(f"{k} {v}")
        for k, hist in self.histograms.items():
            if hist:
                count = len(hist)
                val_sum = sum(hist)
                lines.append(f"{k}_count {count}")
                lines.append(f"{k}_sum {val_sum}")
        return "\n".join(lines) + "\n"


_state = MetricsState()


def inc(name: str, value: float = 1.0, **labels):
    _state.inc(name, value, **labels)


def set_gauge(name: str, value: float, **labels):
    _state.set_gauge(name, value, **labels)


def observe(name: str, value: float, **labels):
    _state.observe(name, value, **labels)


def render_prometheus() -> str:
    return _state.render_prometheus()


def observe_latency(name: str, **labels):
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return await func(*args, **kwargs)
            finally:
                observe(name, (time.perf_counter() - start) * 1000, **labels)

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                observe(name, (time.perf_counter() - start) * 1000, **labels)

        import asyncio

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator
