from types import SimpleNamespace

import pandas as pd
import pytest

from src.domain.datacenter import DataCenter
from src.domain.task import Task
from src.strategies.allocation.custom_weighted import WeightedCustomStrategy
from src.strategies.electricity.custom_parameterized import GridResponsivePricing


def test_custom_weighted_strategy_combines_price_and_projected_load():
    task = Task(user_id="u", task_type="general", required_compute=20, duration_hours=1)
    cheap_busy = DataCenter(id="cheap", name="cheap", region="a", total_compute=100, used_compute=80, current_price=1.0)
    costly_idle = DataCenter(id="idle", name="idle", region="a", total_compute=100, used_compute=0, current_price=1.2)
    strategy = WeightedCustomStrategy(weights={"price": 0.2, "load": 0.8, "carbon": 0, "latency": 0})

    choice = strategy.allocate(task, [cheap_busy, costly_idle], {})

    assert choice.id == "idle"


def test_custom_weighted_strategy_can_forbid_cross_region_allocation():
    task = Task(user_id="u", task_type="general", region="a", required_compute=1, duration_hours=1)
    local = DataCenter(id="local", name="local", region="a", total_compute=10, current_price=5)
    remote = DataCenter(id="remote", name="remote", region="b", total_compute=10, current_price=1)
    strategy = WeightedCustomStrategy(weights={"price": 1}, allow_cross_region=False)

    assert strategy.allocate(task, [local, remote], {}).id == "local"


def test_custom_weighted_strategy_rejects_all_zero_weights():
    with pytest.raises(ValueError, match="at least one"):
        WeightedCustomStrategy(weights={"price": 0, "load": 0, "carbon": 0, "latency": 0})


def test_grid_responsive_price_uses_node_load_compute_load_and_voltage():
    network = SimpleNamespace(
        load=pd.DataFrame([{"bus": 3, "p_mw": 100.0}, {"bus": 4, "p_mw": 20.0}]),
        res_bus=pd.DataFrame({"vm_pu": {3: 0.97, 4: 1.0}}),
    )
    strategy = GridResponsivePricing(
        base_price=0.45,
        local_load_coefficient=0.0002,
        compute_load_coefficient=0.002,
        voltage_deviation_coefficient=1.5,
        minimum_price=0.2,
        maximum_price=1.5,
    )

    assert strategy.get_node_price(network, 3, 10.0) == pytest.approx(0.535)


def test_grid_responsive_price_rejects_reversed_bounds():
    with pytest.raises(ValueError, match="minimum_price"):
        GridResponsivePricing(minimum_price=2.0, maximum_price=1.0)
