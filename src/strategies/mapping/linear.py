# src/strategies/mapping/linear.py
from typing import Dict
from .base import MappingStrategy
from src.domain.task import Task


class LinearMapping(MappingStrategy):
    #任务类型功耗系数
    TYPE_POWER_FACTORS: Dict[str, float] = {
        "ai_training": 1.8,  # AI训练：GPU满载，高功耗
        "scientific": 1.2,  # 科学计算：高内存带宽
        "rendering": 1.5,  # 渲染：GPU持续高负载
        "web_service": 0.4,  # Web服务：低负载，间歇性
        "general": 0.7,  # 通用计算：中等负载
        "default": 0.5
    }

    def __init__(self, base_coefficient: float = 0.5,
                 gpu_scale_factor: float = 0.9,
                 custom_factors: Dict[str, float] = None):

        self.base_coefficient = base_coefficient
        self.gpu_scale_factor = gpu_scale_factor

        # 合并自定义系数
        if custom_factors:
            self.TYPE_POWER_FACTORS.update(custom_factors)

    def map_to_power(self, task: Task) -> float:

        # 获取任务类型
        task_type = getattr(task, 'task_type', 'default')
        if not task_type or task_type not in self.TYPE_POWER_FACTORS:
            task_type = 'default'
        type_factor = self.TYPE_POWER_FACTORS[task_type]

        # 计算GPU修正系数
        plan_gpu = getattr(task, 'plan_gpu', 0) or 0
        if plan_gpu > 0:
            # GPU百分比 → 完整GPU数量
            gpu_ratio = plan_gpu / 100.0
            gpu_count = gpu_ratio * 2  # 假设100% GPU = 2个GPU

            # 多GPU亚线性功耗模型
            if gpu_count <= 1:
                gpu_factor = 1.0
            else:
                # 1个GPU为1，2个GPU为1.8，4个GPU为3.2
                gpu_factor = 1.0 + (gpu_count - 1) * self.gpu_scale_factor
        else:
            # 无GPU任务（纯CPU），功耗相对较低
            gpu_factor = 0.6

        # 计算最终功率
        power_mw = self.base_coefficient * task.required_compute * type_factor * gpu_factor

        # 最小值保护
        return max(0.1, power_mw)

    def get_type_factor(self, task_type: str) -> float:
        """查询某任务类型的功耗系数"""
        return self.TYPE_POWER_FACTORS.get(task_type, self.TYPE_POWER_FACTORS['default'])

    def update_type_factor(self, task_type: str, factor: float):
        """动态更新某任务类型的功耗系数"""
        self.TYPE_POWER_FACTORS[task_type] = factor