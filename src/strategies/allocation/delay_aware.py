from src.domain.datacenter import DataCenter
from src.domain.task import Task
from .base import AllocationStrategy


class DelayAwareStrategy(AllocationStrategy):
    def allocate(self, task: Task, data_centers: list[DataCenter], snapshot: dict | None = None) -> DataCenter:
        eligible = [dc for dc in data_centers if dc.can_allocate(task)]
        if not eligible:
            raise ValueError("no eligible data center")
        latency = (snapshot or {}).get("latency_ms", {})
        return min(eligible, key=lambda dc: latency.get((task.region, dc.region), 20.0))
