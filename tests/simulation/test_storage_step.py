from datetime import datetime

import pytest

from src.domain.storage import EnergyStorage
from src.simulation.engine import SimulationEngine
from src.strategies.electricity.fixed_tou import FixedTimeOfUsePricing


class FakeGrid:
    def __init__(self, net_load_mw=100.0):
        self.storage = []
        self.net_load_mw = net_load_mw

    def update_storage_power(self, bus_id, power):
        self.storage.append((bus_id, power))

    def get_voltage_health(self):
        return {"status": "normal", "min_voltage_pu": 1.0, "max_voltage_pu": 1.0, "violating_buses": 0}

    def get_line_health(self):
        return {"status": "normal", "max_loading_pct": 70.0, "overloaded_lines": 0}

    def estimate_net_load_mw(self, second):
        return self.net_load_mw

    def get_bus_marginal_price(self, bus_id):
        return 0.5



def storage_engine_at(hour):
    engine = object.__new__(SimulationEngine)
    engine.storages = {
        "s": EnergyStorage(
            id="s", bus_id=3, capacity_mwh=10, max_power_mw=4,
            initial_soc_mwh=5, min_soc_mwh=1,
        )
    }
    engine.pp_adapter = FakeGrid()
    engine.step_seconds = 3600
    engine.current_second = hour * 3600
    engine.simulation_start_time = datetime(2026, 1, 1)
    engine.fixed_pricing = FixedTimeOfUsePricing([
        {"start_hour": 0, "end_hour": 7, "price": 0.2},
        {"start_hour": 7, "end_hour": 17, "price": 0.5},
        {"start_hour": 17, "end_hour": 22, "price": 1.0},
        {"start_hour": 22, "end_hour": 24, "price": 0.2},
    ])
    engine.optimization_config = {
        "mode": "none",
        "weights": {"peak_shaving": 1.0, "cost": 0.0, "storage_degradation": 0.0},
    }
    engine.storage_control_config = {"deadband_mw": 0.5, "reference_alpha": 0.05}
    engine._storage_load_reference_mw = 100.0
    return engine


def test_engine_applies_storage_power_to_its_grid_adapter():
    engine = object.__new__(SimulationEngine)
    engine.storages = {"s": EnergyStorage(id="s", bus_id=3, capacity_mwh=10, max_power_mw=4, initial_soc_mwh=5)}
    engine.pp_adapter = FakeGrid()

    engine.apply_storage_dispatch({"s": 2.0}, step_hours=1)

    assert engine.pp_adapter.storage == [(3, 2.0)]
    assert engine.storages["s"].soc_mwh < 5


def test_automatic_storage_charges_when_realtime_net_load_is_below_reference():
    engine = storage_engine_at(2)
    engine.pp_adapter.net_load_mw = 90.0

    engine._dispatch_storage()

    assert engine.storages["s"].current_power_mw == -4.0
    assert engine.storage_dispatch_result["reason"] == "realtime_valley_charging"
    assert engine.storages["s"].soc_mwh > 5


def test_automatic_storage_responds_to_small_peak_deviation():
    engine = storage_engine_at(18)
    engine.pp_adapter.net_load_mw = 101.0

    engine._dispatch_storage()

    assert engine.storages["s"].current_power_mw > 0.0


def test_automatic_storage_discharges_when_realtime_net_load_is_above_reference():
    engine = storage_engine_at(18)
    engine.pp_adapter.net_load_mw = 110.0

    engine._dispatch_storage()

    assert engine.storages["s"].current_power_mw > 0
    assert engine.storage_dispatch_result["reason"] == "realtime_peak_discharging"
    assert engine.storages["s"].soc_mwh < 5


def test_grid_violation_overrides_valley_charging_with_discharge():
    engine = storage_engine_at(2)
    engine.pp_adapter.get_voltage_health = lambda: {
        "status": "out_of_range", "min_voltage_pu": 0.88,
        "max_voltage_pu": 1.06, "violating_buses": 12,
    }
    engine.pp_adapter.get_line_health = lambda: {
        "status": "overloaded", "max_loading_pct": 135.39,
        "overloaded_lines": 2,
    }

    engine._dispatch_storage()

    assert engine.storages["s"].current_power_mw > 0
    assert engine.storage_dispatch_result["reason"] == "grid_support_discharging"


def test_storage_runtime_summary_exposes_power_soc_and_control_reason():
    engine = storage_engine_at(2)
    engine.pp_adapter.net_load_mw = 90.0
    engine._dispatch_storage()

    summary = engine._storage_runtime_summary()

    assert summary["storage_power_mw"] == -4.0
    assert summary["storage_soc_pct"] == pytest.approx(88.0)
    assert summary["storage_dispatch_status"] == "active"
    assert summary["storage_dispatch_reason"] == "realtime_valley_charging"
    assert summary["storage_price"] == 0.2


def test_optimized_storage_reuses_last_power_between_solver_intervals(monkeypatch):
    engine = storage_engine_at(18)
    engine.optimization_config["mode"] = "hierarchical"
    engine.storage_control_config["optimization_interval_seconds"] = 5
    engine.step_seconds = 1
    engine.pp_adapter.net_load_mw = 110.0
    calls = []

    def solve(self, storage, **kwargs):
        calls.append(kwargs["net_load_mw"])
        return {"status": "optimal", "objective_value": 1.0, "power_mw": 2.0}

    monkeypatch.setattr("src.simulation.engine.CoptOptimizer.optimize_storage_realtime", solve)
    engine.current_second = 10
    engine._dispatch_storage()
    engine.current_second = 11
    engine._dispatch_storage()

    assert calls == [110.0]
    assert engine.storage_dispatch_result["actual_power_mw"] == 2.0


def test_optimized_storage_replaces_held_discharge_with_actual_green_surplus_charge():
    engine = storage_engine_at(18)
    engine.optimization_config["mode"] = "joint"
    engine.storages["s"].current_power_mw = 2.0
    engine.pp_adapter.get_renewable_dispatch_summary = lambda: {
        "wind": {"available_mw": 140.0, "dispatched_mw": 100.0, "curtailed_mw": 40.0},
        "pv": {"available_mw": 0.0, "dispatched_mw": 0.0, "curtailed_mw": 0.0},
    }

    engine._advance_optimized_storage()

    assert engine.storages["s"].current_power_mw < 0.0
    assert engine.storages["s"].soc_mwh > 5.0


def test_high_soc_storage_discharges_when_available_renewables_drop():
    engine = storage_engine_at(18)
    engine.pp_adapter.net_load_mw = 120.0
    engine.pp_adapter.get_renewable_dispatch_summary = lambda: {
        "wind": {"available_mw": 8.0, "dispatched_mw": 8.0, "curtailed_mw": 0.0},
        "pv": {"available_mw": 2.0, "dispatched_mw": 2.0, "curtailed_mw": 0.0},
    }
    engine._storage_load_reference_mw = 100.0
    engine._storage_renewable_reference_mw = 40.0
    engine.storages["s"].soc_mwh = 9.0

    engine._dispatch_storage()

    assert engine.storage_dispatch_result["actual_power_mw"] > 0
    assert engine.storage_dispatch_result["reason"] == "renewable_deficit_discharging"


def test_renewable_drop_without_positive_load_deviation_does_not_discharge():
    engine = storage_engine_at(18)
    engine.pp_adapter.net_load_mw = 100.0
    engine.pp_adapter.get_renewable_dispatch_summary = lambda: {
        "wind": {"available_mw": 8.0, "dispatched_mw": 8.0, "curtailed_mw": 0.0},
        "pv": {"available_mw": 2.0, "dispatched_mw": 2.0, "curtailed_mw": 0.0},
    }
    engine._storage_load_reference_mw = 100.0
    engine._storage_renewable_reference_mw = 40.0
    engine.storages["s"].soc_mwh = 9.0

    engine._dispatch_storage()

    assert engine.storage_dispatch_result["actual_power_mw"] <= 1e-9
