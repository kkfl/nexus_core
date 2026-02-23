import structlog

logger = structlog.get_logger(__name__)


# Very basic metrics stub for standard Prometheus scrape
class MetricsState:
    def __init__(self):
        self.counters = {}
        self.gauges = {}

    def inc(self, name: str, value: int = 1, **labels):
        key = (name, tuple(sorted(labels.items())))
        self.counters[key] = self.counters.get(key, 0) + value

    def set_gauge(self, name: str, value: float, **labels):
        key = (name, tuple(sorted(labels.items())))
        self.gauges[key] = value

    def snapshot(self) -> str:
        lines = []
        for (name, labels), val in self.gauges.items():
            label_str = ",".join(f'{k}="{v}"' for k, v in labels)
            lines.append(f"{name}{{{label_str}}} {val}")
        for (name, labels), val in self.counters.items():
            label_str = ",".join(f'{k}="{v}"' for k, v in labels)
            lines.append(f"{name}{{{label_str}}} {val}")
        return "\n".join(lines) + "\n"


_metrics = MetricsState()


def inc(name: str, value: int = 1, **labels):
    _metrics.inc(name, value, **labels)


def set_gauge(name: str, value: float, **labels):
    _metrics.set_gauge(name, value, **labels)


def snapshot() -> str:
    return _metrics.snapshot()
