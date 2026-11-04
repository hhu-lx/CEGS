# src/strategies/electricity/opf.py

import pandapower as pp
import pandas as pd
from .base import ElectricityPricingStrategy


class OPFElectricityPricing(ElectricityPricingStrategy):
    # 默认电价
    DEFAULT_PRICE = 0.5   # 元/kWh

    # 单位转换系数
    MWH_TO_KWH = 0.001

    def __init__(self, default_price: float = None):
        if default_price is not None:
            self.DEFAULT_PRICE = default_price

    def get_node_price(
        self,
        network: pp.pandapowerNet,
        bus_id: int,
        extra_load_mw: float,
        system_extra_load_mw: float = 0.0,
    ) -> float:

        #  检查 res_bus 是否存在
        if not hasattr(network, 'res_bus') or network.res_bus is None:
            return self.DEFAULT_PRICE

        if len(network.res_bus) == 0:
            return self.DEFAULT_PRICE

        #  检查 lam_p 列是否存在
        if 'lam_p' not in network.res_bus.columns:
            return self.DEFAULT_PRICE

        #  检查 bus_id 是否有效
        if bus_id not in network.res_bus.index:
            return self.DEFAULT_PRICE

        #  读取 LMP 值
        lam_p = network.res_bus.loc[bus_id, 'lam_p']

        if pd.isna(lam_p):
            return self.DEFAULT_PRICE

        #  单位转换
        price = float(lam_p) * self.MWH_TO_KWH

        #  合理性检查
        # 若结果异常（如极大值），回退到默认值
        if abs(price) > 10.0:   # 超过 10 元/kWh 视为异常
            return self.DEFAULT_PRICE

        return price

    def get_all_node_prices(self, network: pp.pandapowerNet) -> pd.Series:
        if not hasattr(network, 'res_bus') or 'lam_p' not in network.res_bus.columns:
            return pd.Series(dtype=float)

        prices = network.res_bus['lam_p'] * self.MWH_TO_KWH
        return prices

    def get_price_statistics(self, network: pp.pandapowerNet) -> dict:
        prices = self.get_all_node_prices(network)

        if prices.empty:
            return {
                'mean': self.DEFAULT_PRICE,
                'max': self.DEFAULT_PRICE,
                'min': self.DEFAULT_PRICE,
                'std': 0.0,
                'spread': 0.0
            }

        return {
            'mean': float(prices.mean()),
            'max': float(prices.max()),
            'min': float(prices.min()),
            'std': float(prices.std()),
            'spread': float(prices.max() - prices.min())
        }
