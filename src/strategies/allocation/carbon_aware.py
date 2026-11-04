from src.domain.datacenter import DataCenter
from src.domain.task import Task
from .base import AllocationStrategy


class CarbonAwareStrategy(AllocationStrategy):
    def allocate(self, task: Task, data_centers: list[DataCenter], snapshot: dict | None = None) -> DataCenter:
        eligible = [dc for dc in data_centers if dc.can_allocate(task)]
        if not eligible:
            raise ValueError("no eligible data center")
        intensity = (snapshot or {}).get("carbon_intensity", {})
        return min(eligible, key=lambda dc: intensity.get(dc.grid_bus_id, float("inf")))
