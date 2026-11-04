import pytest

from src.strategies.registry import StrategyRegistry


def test_registry_creates_configured_allocation_strategy():
    strategy = StrategyRegistry().create_allocation("carbon_aware", {})

    assert strategy.__class__.__name__ == "CarbonAwareStrategy"


def test_registry_rejects_unknown_strategy_name():
    with pytest.raises(ValueError, match="unknown allocation strategy"):
        StrategyRegistry().create_allocation("unknown", {})
