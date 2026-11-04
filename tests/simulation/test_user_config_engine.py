import json
from pathlib import Path

import pytest

from src.simulation.engine import SimulationEngine
from src.strategies.allocation.carbon_aware import CarbonAwareStrategy
from src.strategies.electricity.custom_parameterized import GridResponsivePricing


def test_engine_background_thread_starts_only_after_explicit_start(monkeypatch):
    events = []

    class FakeThread:
        def __init__(self, **kwargs):
            events.append(("created", kwargs.get("daemon")))

        def start(self):
            events.append(("started",))

    monkeypatch.setattr("src.simulation.engine.threading.Thread", FakeThread)

    engine = SimulationEngine(user_config={"optimization": {"mode": "none"}})

    assert engine.running is False
    assert events == []
    engine.start()
    assert engine.running is True
    assert events == [("created", True), ("started",)]


def test_engine_uses_uploaded_centers_and_platform_defaults_for_omitted_resources():
    config = {
        "simulation": {"start_datetime": "2030-01-02T03:04:05"},
        "optimization": {"mode": "none"},
        "data_centers": [
            {"id": "DC-A", "name": "A", "region": "a", "grid_bus_id": 1,
             "total_compute": 77, "total_bandwidth": 100, "pue": 1.1, "device_pool": []},
        ],
    }
    engine = SimulationEngine(user_config=config)

    assert engine.simulation_start_time.isoformat() == "2030-01-02T03:04:05"
    assert [(dc.id, dc.total_compute) for dc in engine.data_centers] == [("DC-A", 77)]
    assert [storage.id for storage in engine.storages.values()] == ["storage-1"]


def test_engine_falls_back_to_platform_centers_when_upload_omits_them():
    engine = SimulationEngine(user_config={"optimization": {"mode": "none"}})

    assert [dc.total_compute for dc in engine.data_centers] == [250, 200, 300]
    assert [storage.id for storage in engine.storages.values()] == ["storage-1"]


def test_engine_ui_mode_overrides_user_mode_and_preserves_objective_and_weights():
    engine = SimulationEngine(
        user_config={"optimization": {"mode": "global", "objective": "min_cost", "weights": {"cost": 3}}},
        ui_config={
            "optimization": {"mode": "none"},
            "electricity_pricing": {
                "mode": "fixed_tou",
                "periods": [{"start_hour": 0, "end_hour": 24, "price": 0.27}],
                "file": None,
            },
        },
    )

    assert engine.optimization_config["mode"] == "none"
    assert engine.optimization_config["objective"] == "min_cost"
    assert engine.optimization_config["weights"] == {
        "cost": 3,
        "carbon": 1.5,
        "delay": 0.2,
        "peak_shaving": 2.0,
        "renewable_curtailment": 3.0,
        "storage_degradation": 0.1,
    }
    assert engine.pricing_config["file"] is None
    assert engine.fixed_pricing.periods[0].price == 0.27


def test_engine_uses_frontend_dispatch_strategy_instead_of_always_lowest_price(monkeypatch):
    monkeypatch.setattr("threading.Thread.start", lambda self: None)
    engine = SimulationEngine(
        user_config={"optimization": {"mode": "none"}},
        ui_config={
            "scheduling": {"strategy": "low_carbon"},
            "electricity_pricing": {
                "mode": "fixed_tou",
                "periods": [{"start_hour": 0, "end_hour": 24, "price": 0.27}],
                "file": None,
            },
        },
    )

    assert isinstance(engine.scheduler.strategy, CarbonAwareStrategy)


def test_heuristic_mode_respects_frontend_marginal_pricing_choice(monkeypatch):
    monkeypatch.setattr("threading.Thread.start", lambda self: None)
    engine = SimulationEngine(
        user_config={"optimization": {"mode": "none"}},
        ui_config={
            "scheduling": {"strategy": "lowest_price"},
            "electricity_pricing": {"mode": "marginal", "periods": [], "file": None},
        },
    )

    assert engine.pricing_config["mode"] == "marginal"
    assert engine.fixed_pricing is None


def test_engine_builds_parameterized_custom_pricing_from_frontend(monkeypatch):
    monkeypatch.setattr("threading.Thread.start", lambda self: None)
    engine = SimulationEngine(
        user_config={"optimization": {"mode": "none"}},
        ui_config={
            "scheduling": {"strategy": "lowest_price"},
            "electricity_pricing": {
                "mode": "custom",
                "parameters": {
                    "name": "grid_responsive_price",
                    "base_price": 0.4,
                    "local_load_coefficient": 0.001,
                    "compute_load_coefficient": 0.01,
                    "voltage_deviation_coefficient": 2,
                    "minimum_price": 0.2,
                    "maximum_price": 1.6,
                },
            },
        },
    )

    assert isinstance(engine.pp_adapter.electricity_strategy, GridResponsivePricing)
    assert engine.pp_adapter.electricity_strategy.base_price == 0.4


def test_engine_applies_shared_grid_series_offset_and_renewable_capacities(monkeypatch):
    monkeypatch.setattr("threading.Thread.start", lambda self: None)

    engine = SimulationEngine(user_config={"optimization": {"mode": "none"}})

    assert engine.load_loader.start_offset_seconds == 0
    assert engine.pv_loader.start_offset_seconds == 0
    assert engine.wind_loader.start_offset_seconds == 0
    assert engine.base_generation_loader.start_offset_seconds == 0
    assert engine.pp_adapter.pv_capacity_mw == 2920.0
    assert engine.pp_adapter.wind_capacity_mw == 1300.0
    assert engine.simulation_start_time.hour == 16


def test_engine_rejects_inline_topology_in_frontend_config():
    with pytest.raises(ValueError, match="topology"):
        SimulationEngine(user_config={"topology": {"name": "custom"}}, ui_config={})


def test_engine_keeps_legacy_direct_dict_topology_compatibility():
    topology = json.loads(Path("config/topology_ieee39.json").read_text(encoding="utf-8"))
    engine = SimulationEngine(user_config={"topology": topology})

    assert engine.pp_adapter.topology["name"] == topology["name"]
    assert [dc.id for dc in engine.data_centers] == ["DC1", "DC2", "DC3"]


def test_engine_applies_uploaded_topology_resource_mapping_from_ui_config():
    topology = json.loads(Path("config/topology_ieee39.json").read_text(encoding="utf-8"))
    topology["base_mva"] = 200.0
    topology["resource_mapping"] = {
        "pv_bus": 11,
        "wind_bus": 22,
        "load_buses": [3, 16, 21],
    }

    engine = SimulationEngine(
        user_config={},
        ui_config={
            "topology": topology,
            "electricity_pricing": {"mode": "marginal", "periods": [], "file": None},
        },
    )

    assert engine.pp_adapter.topology["name"] == "IEEE39"
    assert engine.pp_adapter.pv_bus == 11
    assert engine.pp_adapter.wind_bus == 22
    assert engine.pp_adapter.base_mva == 200.0
