# src/strategies/mapping/base.py
from typing import Protocol
from src.domain.task import Task

class MappingStrategy(Protocol):
    """算力→功率映射策略接口"""
    def map_to_power(self, task: Task) -> float:
        """根据任务信息计算功率（MW）"""
        ...