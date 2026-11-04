from typing import Protocol, TYPE_CHECKING
if TYPE_CHECKING:
    from src.domain.datacenter import DataCenter
class PricingStrategy(Protocol):
    """算力定价策略协议：根据电网电价和运行参数计算算力单价"""
    def calculate_price(self, node_price_per_kwh: float, datacenter: 'DataCenter') -> float:
        ...