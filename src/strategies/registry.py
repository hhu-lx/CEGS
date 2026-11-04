from src.strategies.allocation.carbon_aware import CarbonAwareStrategy
from src.strategies.allocation.delay_aware import DelayAwareStrategy
from src.strategies.allocation.load_balanced import LoadBalancedStrategy
from src.strategies.allocation.lowest_price import LowestPriceStrategy
from src.strategies.allocation.custom_weighted import WeightedCustomStrategy


class StrategyRegistry:
    _ALLOCATION = {
        "lowest_price": LowestPriceStrategy,
        "carbon_aware": CarbonAwareStrategy,
        "delay_aware": DelayAwareStrategy,
        "load_balanced": LoadBalancedStrategy,
        "custom_weighted": WeightedCustomStrategy,
    }

    _ALIASES = {
        "low_carbon": "carbon_aware",
        "low_latency": "delay_aware",
        "load_balance": "load_balanced",
    }

    def create_allocation(self, name: str, settings: dict):
        name = self._ALIASES.get(name, name)
        try:
            return self._ALLOCATION[name](**settings)
        except KeyError as error:
            raise ValueError(f"unknown allocation strategy: {name}") from error
