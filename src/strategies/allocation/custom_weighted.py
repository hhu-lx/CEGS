from __future__ import annotations

from src.domain.datacenter import DataCenter
from src.domain.task import Task
from .base import AllocationStrategy


class WeightedCustomStrategy(AllocationStrategy):
    """Safe parameterized allocation using normalized runtime signals."""

    _WEIGHT_NAMES = ("price", "load", "carbon", "latency")

    def __init__(self, weights: dict | None = None, allow_cross_region: bool = True):
        supplied = weights or {}
        unknown = set(supplied) - set(self._WEIGHT_NAMES)
        if unknown:
            raise ValueError(f"unknown weight: {sorted(unknown)[0]}")
        values = {name: float(supplied.get(name, 0.0)) for name in self._WEIGHT_NAMES}
        if any(value < 0 for value in values.values()):
            raise ValueError("custom strategy weights must be non-negative")
        total = sum(values.values())
        if total <= 0:
            raise ValueError("at least one custom strategy weight must be greater than zero")
        self.weights = {name: value / total for name, value in values.items()}
        self.allow_cross_region = bool(allow_cross_region)

    @staticmethod
    def _normalize(values: list[float]) -> list[float]:
        low, high = min(values), max(values)
        if high - low <= 1e-12:
            return [0.0] * len(values)
        return [(value - low) / (high - low) for value in values]

    @staticmethod
    def _latency(task: Task, dc: DataCenter, snapshot: dict) -> float:
        latency = snapshot.get("latency_ms", {})
        explicit = latency.get((task.region, dc.region))
        if explicit is None:
            explicit = latency.get(f"{task.region}->{dc.region}")
        if explicit is not None:
            return float(explicit)
        return 5.0 if task.region == dc.region else 20.0

    def allocate(self, task: Task, data_centers: list[DataCenter], snapshot: dict | None = None) -> DataCenter:
        eligible = [
            dc for dc in data_centers
            if dc.can_allocate(task) and (self.allow_cross_region or dc.region == task.region)
        ]
        if not eligible:
            raise ValueError("no eligible data center for custom strategy")

        snapshot = snapshot or {}
        carbon = snapshot.get("carbon_intensity", {})
        metrics = {
            "price": [float(dc.current_price) for dc in eligible],
            "load": [
                min(1.0, (float(dc.used_compute) + float(task.required_compute)) / float(dc.total_compute))
                for dc in eligible
            ],
            "carbon": [float(carbon.get(dc.grid_bus_id, 0.5)) for dc in eligible],
            "latency": [self._latency(task, dc, snapshot) for dc in eligible],
        }
        normalized = {name: self._normalize(values) for name, values in metrics.items()}

        def score(index: int) -> tuple[float, str]:
            value = sum(self.weights[name] * normalized[name][index] for name in self._WEIGHT_NAMES)
            return value, eligible[index].id

        return eligible[min(range(len(eligible)), key=score)]
