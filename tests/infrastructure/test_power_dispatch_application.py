import pytest
import numpy as np

from src.domain.storage import EnergyStorage
from src.infrastructure.pandapower_adapter import PandapowerAdapter
from src.optimization.power_dispatch import PowerDispatchResult


class Loader:
    def __init__(self, values):
        self.values = list(values)
        self.data = np.asarray(values, dtype=float)
        self.length = len(values)
        self.time_compression = 1.0
        self.start_offset_seconds = 0

    def get_value_at_second(self, second):
        return self.values[int(second // 3600) % len(self.values)]


def result_for(problem, *, generator_value=100.0, wind=8.0, pv=4.0, storage_power=None):
    horizon = 2
    storage_power = storage_power or {}
    return PowerDispatchResult(
        status="optimal",
        objective_value=1.0,
        generator_mw={item.id: [min(generator_value, item.max_mw)] * horizon for item in problem.generators},
        renewable_dispatched_mw={"wind": [wind] * horizon, "pv": [pv] * horizon},
        renewable_curtailed_mw={"wind": [0.0] * horizon, "pv": [0.0] * horizon},
        storage_power_mw={key: [value] * horizon for key, value in storage_power.items()},
        storage_soc_mwh={key: [10.0] * (horizon + 1) for key in storage_power},
        objective_components={},
        strictly_feasible=True,
        forecast_fill="native",
    )


def test_apply_accepts_feasible_time_limited_joint_incumbent():
    adapter = configured_adapter()
    problem = adapter.build_power_dispatch_problem(0, horizon_hours=2)
    result = result_for(problem)
    result = PowerDispatchResult(
        status="optimal_solution",
        objective_value=result.objective_value,
        generator_mw=result.generator_mw,
        renewable_dispatched_mw=result.renewable_dispatched_mw,
        renewable_curtailed_mw=result.renewable_curtailed_mw,
        storage_power_mw=result.storage_power_mw,
        storage_soc_mwh=result.storage_soc_mwh,
        objective_components=result.objective_components,
        strictly_feasible=True,
        forecast_fill=result.forecast_fill,
        external_grid_mw=result.external_grid_mw,
    )
    assert adapter.apply_power_dispatch(result)["dispatch_id"].startswith("dispatch-")


def configured_adapter():
    adapter = PandapowerAdapter(
        load_loader=Loader([0.3, 0.4]),
        pv_loader=Loader([0.1, 0.2]),
        wind_loader=Loader([0.2, 0.3]),
        base_generation_loader=Loader([0.8, 0.9]),
    )
    adapter.set_storage_models([
        EnergyStorage(
            id="battery-a", bus_id=3, capacity_mwh=40.0, max_power_mw=10.0,
            initial_soc_mwh=20.0,
        ),
        EnergyStorage(
            id="battery-b", bus_id=16, capacity_mwh=20.0, max_power_mw=5.0,
            initial_soc_mwh=10.0,
        ),
    ])
    adapter.update_time_series(0)
    return adapter


def test_build_problem_and_apply_period_zero_for_dynamic_device_counts():
    adapter = configured_adapter()

    problem = adapter.build_power_dispatch_problem(0, horizon_hours=2)
    dispatch = result_for(
        problem, generator_value=120.0, storage_power={"battery-a": -3.0, "battery-b": 2.0}
    )
    applied = adapter.apply_power_dispatch(dispatch)

    assert len(problem.generators) == len(adapter._base_generation_nominal)
    assert len(problem.storages) == 2
    assert all(not item.reference_mw for item in problem.generators)
    assert set(problem.renewables[i].id for i in range(len(problem.renewables))) == {"wind", "pv"}
    assert problem.forecast_fill == "cyclic"
    assert applied["generator_mw"] == {
        item.id: pytest.approx(min(120.0, item.max_mw)) for item in problem.generators
    }
    assert adapter.renewable_dispatched_mw == {"wind": 8.0, "pv": 4.0}
    assert adapter.storage_powers == {3: -3.0, 16: 2.0}
    assert adapter.storage_models["battery-a"].soc_mwh == pytest.approx(20.0)
    assert adapter.storage_models["battery-b"].soc_mwh == pytest.approx(10.0)


def test_apply_dispatch_sums_multiple_storage_units_on_the_same_bus():
    adapter = configured_adapter()
    adapter.storage_models["battery-b"].bus_id = 3
    problem = adapter.build_power_dispatch_problem(0, horizon_hours=2)

    adapter.apply_power_dispatch(result_for(
        problem, storage_power={"battery-a": -3.0, "battery-b": 2.0}
    ))

    assert adapter.storage_powers == {3: pytest.approx(-1.0)}


def test_optimized_generation_is_not_overwritten_by_reference_profile():
    adapter = configured_adapter()
    problem = adapter.build_power_dispatch_problem(0, horizon_hours=2)
    adapter.apply_power_dispatch(result_for(problem, generator_value=123.0))
    expected = adapter.network.gen.loc[list(adapter._dispatch_generator_indices.values()), "p_mw"].copy()

    adapter.update_time_series(3600)

    assert adapter.network.gen.loc[expected.index, "p_mw"].tolist() == pytest.approx(expected.tolist())


def test_ac_invalid_dispatch_rolls_back_all_device_values(monkeypatch):
    adapter = configured_adapter()
    problem = adapter.build_power_dispatch_problem(0, horizon_hours=2)
    first = result_for(
        problem, generator_value=100.0, wind=7.0, pv=3.0,
        storage_power={"battery-a": -2.0, "battery-b": 1.0},
    )
    first_apply = adapter.apply_power_dispatch(first)

    monkeypatch.setattr(adapter, "run_power_flow", lambda: setattr(adapter, "_power_flow_valid", True))
    monkeypatch.setattr(adapter, "get_operating_constraint_snapshot", lambda *args, **kwargs: {"feasible": True})
    valid = adapter.validate_dispatch_ac()
    assert valid["feasible"] is True

    # Physical time may advance after the last AC-valid snapshot. A rejected
    # candidate must restore controls without rewinding that elapsed SOC.
    adapter.storage_models["battery-a"].soc_mwh = 19.25
    adapter.storage_models["battery-a"].current_power_mw = 0.5

    second = result_for(
        problem, generator_value=250.0, wind=1.0, pv=1.0,
        storage_power={"battery-a": 5.0, "battery-b": -4.0},
    )
    adapter.apply_power_dispatch(second)
    monkeypatch.setattr(adapter, "get_operating_constraint_snapshot", lambda *args, **kwargs: {"feasible": False})
    assert adapter.validate_dispatch_ac()["feasible"] is False

    restored = adapter.restore_last_feasible_dispatch()

    assert restored is True
    assert adapter.current_dispatch_id == first_apply["dispatch_id"]
    assert adapter.renewable_dispatched_mw == {"wind": 7.0, "pv": 3.0}
    assert adapter.storage_powers == {3: -2.0, 16: 1.0}
    assert adapter.storage_models["battery-a"].soc_mwh == pytest.approx(19.25)
    assert adapter.storage_models["battery-a"].current_power_mw == pytest.approx(0.5)
    for item in problem.generators:
        index = adapter._dispatch_generator_indices[item.id]
        assert adapter.network.gen.at[index, "p_mw"] == pytest.approx(min(100.0, item.max_mw))

