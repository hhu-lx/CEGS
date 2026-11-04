from src.domain.datacenter import DataCenter
from src.domain.task import Task
from .base import AllocationStrategy


class LoadBalancedStrategy(AllocationStrategy):
    def allocate(self, task: Task, data_centers: list[DataCenter], snapshot: dict | None = None) -> DataCenter:
        eligible = [dc for dc in data_centers if dc.can_allocate(task)]
        if not eligible:
            raise ValueError("no eligible data center")
        return min(eligible, key=lambda dc: dc.used_compute / dc.total_compute)
