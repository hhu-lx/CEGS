# src/domain/grid.py
from typing import Optional
from pydantic import BaseModel, Field

class GridNode(BaseModel):
    bus_id: int                              # pandapower节点索引
    region: str                               # 所属区域
    voltage_kv: float = 110.0                 # 基准电压（kV）
    load_mw: float = 0.0                      # 当前负荷（MW）
    generation_mw: float = 0.0                # 当前发电（MW）
    price_per_kwh: Optional[float] = None     # 当前节点电价（元/kWh），由潮流计算后更新

    @property
    def net_load(self) -> float:
        return self.load_mw - self.generation_mw