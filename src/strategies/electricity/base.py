from typing import Protocol
import pandapower as pp

class ElectricityPricingStrategy(Protocol):
    """电网电价计算策略：根据电网状态计算节点电价"""
    def get_node_price(
        self,
        network: pp.pandapowerNet,
        bus_id: int,
        extra_load_mw: float = 0.0,
        system_extra_load_mw: float = 0.0,
    ) -> float:
        ...
