from typing import List
from src.domain.task import Task
from src.domain.datacenter import DataCenter
from src.strategies.allocation.base import AllocationStrategy

class Scheduler:
    #调度中心：根据策略选择最合适的数据中心
    def __init__(self, strategy: AllocationStrategy):
        self.strategy = strategy

    def select_data_center(
        self,
        task: Task,
        data_centers: List[DataCenter],
        snapshot: dict | None = None,
    ) -> DataCenter:
        #调用策略分配任务
        return self.strategy.allocate(task, data_centers, snapshot)
