from typing import List
from src.domain.task import Task
from src.domain.datacenter import DataCenter

class AllocationStrategy:
    """分配策略协议（接口），所有策略必须实现 allocate 方法"""
    def allocate(self, task: Task, data_centers: List[DataCenter], snapshot: dict | None = None) -> DataCenter:
        raise NotImplementedError
