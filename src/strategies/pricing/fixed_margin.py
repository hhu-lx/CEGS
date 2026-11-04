from .base import PricingStrategy
from src.domain.datacenter import DataCenter

class FixedMarginPricing(PricingStrategy):
    """固定利润加成定价策略"""
    def calculate_price(self, node_price_per_kwh: float, datacenter: DataCenter) -> float:
        # 电费成本 = 电价 * 功耗系数 * 1000 (MW->kW)
        electricity_cost = node_price_per_kwh * datacenter.power_per_tflops * 1000
        # 乘以利润加成
        return electricity_cost * datacenter.profit_margin