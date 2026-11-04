import csv
import statistics

import pytest

from src.infrastructure.pandapower_adapter import PandapowerAdapter
from src.loaders.ts_loader import TimeSeriesDataLoader
from src.loaders.config_loader import get_grid_config, load_platform_config
from src.loaders.topology_loader import load_topology


def test_platform_base_generation_plan_covers_about_eighty_five_percent_of_actual_load():
    config = load_platform_config()
    grid = get_grid_config(config)
    with open(grid["load_file"], encoding="utf-8-sig") as source:
        load_pu = [float(row[0]) for row in csv.reader(source) if row]
    with open(grid["base_generation_file"], encoding="utf-8-sig") as source:
        generation_pu = [float(row[0]) for row in csv.reader(source) if row]

    # The adapter normalizes the supplied load profile by its mean before
    # applying ``load_capacity_mw``.  Measure against that actual injected
    # MW value, rather than treating the raw profile as a capacity fraction.
    mean_load_pu = statistics.mean(load_pu)
    coverage = [
        generation * float(grid["base_generation_capacity_mw"])
        / (load * float(grid["load_capacity_mw"]) / mean_load_pu)
        for load, generation in zip(load_pu, generation_pu)
    ]

    assert len(coverage) == 86400
    assert statistics.mean(coverage) == pytest.approx(0.85, abs=0.01)
    assert max(coverage) - min(coverage) >= 0.03


def test_storage_power_creates_load_when_charging_and_generation_when_discharging():
    adapter = PandapowerAdapter()
    adapter.update_storage_power(bus_id=3, net_power_mw=-2.0)
    adapter.update_time_series(1)

    assert adapter.get_storage_net_power(3) == -2.0
    assert (adapter.network.load["bus"] == 3).any()

    adapter.update_storage_power(bus_id=3, net_power_mw=2.0)
    adapter.update_time_series(2)

    assert adapter.get_storage_net_power(3) == 2.0
    assert (adapter.network.sgen["bus"] == 3).any()


def test_power_dispatch_uses_configured_external_grid_import_limit():
    adapter = PandapowerAdapter(external_grid_max_import_mw=2200.0)

    problem = adapter.build_power_dispatch_problem(0, horizon_hours=1)

    assert problem.external_grid_max_import_mw == pytest.approx(2200.0)


def test_topology_generators_dispatch_against_full_load_not_platform_base_plan():
    class Loader:
        def __init__(self, value):
            self.value = value

        def get_value_at_second(self, second):
            return self.value

    topology = load_topology("config/examples/custom_topology_test.json")
    adapter = PandapowerAdapter(
        load_loader=Loader(0.5),
        pv_loader=Loader(0.0),
        wind_loader=Loader(0.0),
        base_generation_loader=Loader(0.95),
        topology=topology,
        load_capacity_mw=600.0,
        base_generation_capacity_mw=600.0,
        use_topology_generators=True,
    )

    problem = adapter.build_power_dispatch_problem(0, horizon_hours=1)

    assert len(problem.generators) == 2
    assert problem.fixed_generation_mw == []
    assert problem.load_mw == pytest.approx([600.0])


def test_base_generation_pu_is_system_level_fixed_injection():
    loader = TimeSeriesDataLoader("tests/fixtures/base_generation_test.csv", "基础发电", 1.0)
    adapter = PandapowerAdapter(base_generation_loader=loader)
    nominal = adapter._base_generation_nominal.copy()

    adapter.update_time_series(0)
    assert adapter.network.gen.loc[0, "p_mw"] == nominal.loc[0]
    assert adapter.network.sgen.iloc[-1]["p_mw"] == pytest.approx(80.0)

    adapter.update_time_series(1)
    assert adapter.network.gen.loc[0, "p_mw"] == nominal.loc[0]
    assert adapter.network.sgen.iloc[-1]["p_mw"] == pytest.approx(90.0)


def test_base_generation_capacity_can_exceed_network_base_mva():
    loader = TimeSeriesDataLoader("tests/fixtures/base_generation_test.csv", "基础发电", 1.0)
    adapter = PandapowerAdapter(
        base_generation_loader=loader,
        base_mva=100.0,
        base_generation_capacity_mw=500.0,
    )

    adapter.update_time_series(1)

    assert adapter.network.sgen.iloc[-1]["p_mw"] == pytest.approx(450.0)


def test_adapter_exposes_live_generation_grid_exchange_and_reserve_metrics():
    class Loader:
        def __init__(self, value):
            self.value = value

        def get_value_at_second(self, second):
            return self.value

    adapter = PandapowerAdapter(
        load_loader=Loader(0.3), pv_loader=Loader(0.1), wind_loader=Loader(0.2)
    )
    adapter.update_time_series(1)
    adapter.run_power_flow()

    assert adapter.get_renewable_generation() == {"wind_mw": 20.0, "pv_mw": 10.0}
    assert adapter.get_grid_exchange_mw() is not None
    assert adapter.get_reserve_capacity_mw() is not None
    assert adapter.network.res_bus.vm_pu.notna().all()
    assert adapter.get_line_health()["max_loading_pct"] is not None


def test_load_timeseries_replaces_topology_static_load_for_final_injection():
    class Loader:
        def get_value_at_second(self, second):
            return 0.3

    adapter = PandapowerAdapter(load_loader=Loader(), base_mva=100.0)
    adapter.update_time_series(1)

    # A constant profile keeps the topology's nominal system scale, while
    # the profile itself remains the sole source of time variation.
    assert adapter.get_total_load() == pytest.approx(adapter._topology_static_load_mw)
    assert adapter._base_static_load_mw == pytest.approx(0.0)


def test_user_timeseries_can_replace_topology_load_scale_and_generators():
    class Loader:
        def __init__(self, value):
            self.value = value

        def get_value_at_second(self, second):
            return self.value

    adapter = PandapowerAdapter(
        load_loader=Loader(0.5),
        base_generation_loader=Loader(0.95),
        load_capacity_mw=600.0,
        base_generation_capacity_mw=600.0,
        use_topology_generators=False,
    )
    adapter.update_time_series(0)

    assert adapter.get_total_load() == pytest.approx(600.0)
    assert not adapter._dispatch_generator_indices
    assert adapter.network.gen["p_mw"].sum() == pytest.approx(570.0)
    assert adapter._last_base_generation_mw == pytest.approx(570.0)


def test_renewable_absorption_limit_excludes_planned_base_generation():
    class Loader:
        def __init__(self, value):
            self.value = value

        def get_value_at_second(self, second):
            return self.value

    adapter = PandapowerAdapter(
        load_loader=Loader(0.5),
        base_generation_loader=Loader(0.95),
        load_capacity_mw=600.0,
        base_generation_capacity_mw=600.0,
        use_topology_generators=False,
    )
    adapter.update_time_series(0)

    assert adapter.get_renewable_absorption_limit_mw() == pytest.approx(30.0)


def test_fixed_base_plan_is_not_reduced_when_wind_is_available():
    class Loader:
        def __init__(self, value):
            self.value = value

        def get_value_at_second(self, second):
            return self.value

    adapter = PandapowerAdapter(
        load_loader=Loader(0.5),
        wind_loader=Loader(0.8),
        base_generation_loader=Loader(0.95),
        load_capacity_mw=600.0,
        base_generation_capacity_mw=600.0,
        wind_capacity_mw=400.0,
        use_topology_generators=False,
    )
    adapter.update_time_series(0)

    # The conventional plan is a committed fixed injection.  Wind above
    # the 30 MW residual demand must be curtailed rather than replacing it.
    assert adapter._last_base_generation_mw == pytest.approx(570.0)


def test_data_driven_dispatch_keeps_base_plan_fixed_and_curtails_surplus_wind():
    class Loader:
        def __init__(self, value):
            self.value = value

        def get_value_at_second(self, second):
            return self.value

    adapter = PandapowerAdapter(
        load_loader=Loader(0.5),
        wind_loader=Loader(0.8),
        base_generation_loader=Loader(0.95),
        load_capacity_mw=600.0,
        base_generation_capacity_mw=600.0,
        wind_capacity_mw=400.0,
        use_topology_generators=False,
    )

    problem = adapter.build_power_dispatch_problem(0, horizon_hours=1)

    assert problem.load_mw == pytest.approx([600.0])
    assert problem.fixed_generation_mw == pytest.approx([280.0])
    assert problem.renewables[0].available_mw == pytest.approx([320.0])
    assert problem.external_grid_max_export_mw == pytest.approx(0.0)


def test_first_dispatch_period_can_use_actual_renewable_and_recompute_base_plan():
    class Loader:
        def __init__(self, value):
            self.value = value

        def get_value_at_second(self, second):
            return self.value

    adapter = PandapowerAdapter(
        load_loader=Loader(0.5),
        wind_loader=Loader(0.2),
        base_generation_loader=Loader(0.95),
        load_capacity_mw=600.0,
        base_generation_capacity_mw=600.0,
        wind_capacity_mw=400.0,
        use_topology_generators=False,
    )
    adapter.update_time_series(0)

    problem = adapter.build_power_dispatch_problem(
        0,
        horizon_hours=1,
        actual_renewable_first_period={"wind": 400.0, "pv": 0.0},
    )

    assert problem.renewables[0].available_mw[0] == pytest.approx(400.0)
    assert problem.fixed_generation_mw[0] == pytest.approx(200.0)


def test_renewable_curtailment_does_not_increase_fixed_base_generation():
    class Loader:
        def __init__(self, value):
            self.value = value

        def get_value_at_second(self, second):
            return self.value

    adapter = PandapowerAdapter(
        load_loader=Loader(0.5), wind_loader=Loader(0.8),
        base_generation_loader=Loader(0.95),
        load_capacity_mw=600.0, base_generation_capacity_mw=600.0,
        wind_capacity_mw=400.0, use_topology_generators=False,
    )
    adapter.update_time_series(0)
    adapter.apply_renewable_dispatch({"wind": 160.0})

    # An AC-driven renewable curtailment leaves the committed plan intact.
    assert adapter._last_base_generation_mw == pytest.approx(570.0)


def test_renewable_dispatch_tracks_available_consumed_and_curtailed_power():
    class Loader:
        def __init__(self, value):
            self.value = value

        def get_value_at_second(self, second):
            return self.value

    adapter = PandapowerAdapter(pv_loader=Loader(0.1), wind_loader=Loader(0.2))
    adapter.update_time_series(1)
    adapter.apply_renewable_dispatch({"wind": 12.0, "pv": 4.0})

    assert adapter.get_renewable_dispatch_summary() == {
        "wind": {"available_mw": 20.0, "dispatched_mw": 12.0, "curtailed_mw": 8.0},
        "pv": {"available_mw": 10.0, "dispatched_mw": 4.0, "curtailed_mw": 6.0},
    }


def test_topology_node_power_loaders_inject_direct_mw_without_split_coefficients():
    class Loader:
        def __init__(self, value):
            self.value = value

        def get_value_at_second(self, second):
            return self.value

    adapter = PandapowerAdapter(
        renewable_node_loaders=[
            {"type": "wind", "bus_id": 20, "loader": Loader(65.0)},
            {"type": "wind", "bus_id": 3, "loader": Loader(65.0)},
            {"type": "pv", "bus_id": 10, "loader": Loader(30.0)},
            {"type": "pv", "bus_id": 16, "loader": Loader(70.0)},
        ]
    )

    adapter.update_time_series(0)

    assert adapter.get_renewable_dispatch_summary() == {
        "wind": {"available_mw": 130.0, "dispatched_mw": 130.0, "curtailed_mw": 0.0},
        "pv": {"available_mw": 100.0, "dispatched_mw": 100.0, "curtailed_mw": 0.0},
    }
    assert adapter.network.gen.loc[adapter.renewable_gen_indices["wind"], "p_mw"].sum() == pytest.approx(130.0)
    assert adapter.network.gen.loc[adapter.renewable_gen_indices["pv"], "p_mw"].sum() == pytest.approx(100.0)


def test_power_dispatch_forecast_uses_direct_topology_node_mw_profiles():
    class Loader:
        def __init__(self, value):
            self.value = value

        def get_value_at_second(self, second):
            return self.value

    adapter = PandapowerAdapter(
        renewable_node_loaders=[
            {"type": "wind", "bus_id": 20, "loader": Loader(65.0)},
            {"type": "wind", "bus_id": 3, "loader": Loader(65.0)},
            {"type": "pv", "bus_id": 10, "loader": Loader(30.0)},
            {"type": "pv", "bus_id": 16, "loader": Loader(70.0)},
        ]
    )

    problem = adapter.build_power_dispatch_problem(0, horizon_hours=1)

    forecast = {item.id: item.available_mw for item in problem.renewables}
    assert forecast == {"wind": [130.0], "pv": [100.0]}


def test_renewable_profiles_use_installed_capacity_instead_of_grid_base_mva():
    class Loader:
        def __init__(self, value):
            self.value = value

        def get_value_at_second(self, second):
            return self.value

    adapter = PandapowerAdapter(
        pv_loader=Loader(0.1),
        wind_loader=Loader(0.2),
        pv_capacity_mw=900.0,
        wind_capacity_mw=1300.0,
    )

    adapter.update_time_series(0)
    adapter.apply_renewable_dispatch({"wind": 200.0, "pv": 70.0})

    assert adapter.get_renewable_dispatch_summary() == {
        "wind": {"available_mw": 260.0, "dispatched_mw": 200.0, "curtailed_mw": 60.0},
        "pv": {"available_mw": 90.0, "dispatched_mw": 70.0, "curtailed_mw": 20.0},
    }


def test_secondary_renewable_nodes_split_output_without_changing_total():
    class Loader:
        def get_value_at_second(self, second):
            return 0.5

    adapter = PandapowerAdapter(
        pv_loader=Loader(), wind_loader=Loader(),
        pv_capacity_mw=100.0, wind_capacity_mw=200.0,
        pv_secondary_bus=16, wind_secondary_bus=21,
        pv_secondary_ratio=0.5, wind_secondary_ratio=0.5,
    )
    adapter.update_time_series(0)

    assert len(adapter.renewable_gen_indices["pv"]) == 2
    assert len(adapter.renewable_gen_indices["wind"]) == 2
    assert adapter.get_renewable_dispatch_summary()["pv"]["dispatched_mw"] == pytest.approx(50.0)
    assert adapter.get_renewable_dispatch_summary()["wind"]["dispatched_mw"] == pytest.approx(100.0)


def test_voltage_health_reports_current_bus_range_separately_from_cpf_margin():
    adapter = PandapowerAdapter()
    adapter.run_power_flow()

    health = adapter.get_voltage_health()

    assert health["status"] in {"normal", "out_of_range"}
    assert health["min_voltage_pu"] == pytest.approx(float(adapter.network.res_bus.vm_pu.min()))
    assert health["max_voltage_pu"] == pytest.approx(float(adapter.network.res_bus.vm_pu.max()))
    assert health["violating_buses"] >= 0


def test_heuristic_preserves_all_renewables_when_grid_limits_are_met(monkeypatch):
    class Loader:
        def get_value_at_second(self, second):
            return 0.1

    adapter = PandapowerAdapter(pv_loader=Loader(), wind_loader=Loader())
    adapter.update_time_series(1)
    monkeypatch.setattr(adapter, "run_power_flow", lambda: None)
    monkeypatch.setattr(adapter, "get_operating_constraint_snapshot", lambda *args: {"feasible": True})

    result = adapter.apply_heuristic_renewable_curtailment()

    assert result == {"status": "full", "dispatch_factor": 1.0}
    assert all(data["curtailed_mw"] == 0.0 for data in adapter.get_renewable_dispatch_summary().values())


def test_heuristic_does_not_discard_renewables_when_violation_is_unaffected_by_curtailment(monkeypatch):
    class Loader:
        def get_value_at_second(self, second):
            return 0.1

    adapter = PandapowerAdapter(pv_loader=Loader(), wind_loader=Loader())
    adapter.update_time_series(1)
    monkeypatch.setattr(adapter, "run_power_flow", lambda: None)
    monkeypatch.setattr(adapter, "get_operating_constraint_snapshot", lambda *args: {
        "feasible": False, "min_voltage_pu": 0.92, "max_voltage_pu": 1.06, "max_line_loading_pct": 80.0,
    })

    result = adapter.apply_heuristic_renewable_curtailment(iterations=4)

    assert result["status"] == "grid_infeasible"
    assert result["dispatch_factor"] == 1.0
    assert sum(value["curtailed_mw"] for value in adapter.get_renewable_dispatch_summary().values()) == 0.0


def test_heuristic_finds_highest_feasible_renewable_output(monkeypatch):
    class Loader:
        def __init__(self, value):
            self.value = value

        def get_value_at_second(self, second):
            return self.value

    adapter = PandapowerAdapter(pv_loader=Loader(0.1), wind_loader=Loader(0.2))
    adapter.update_time_series(1)
    monkeypatch.setattr(adapter, "run_power_flow", lambda: None)

    def snapshot(*args):
        total = sum(adapter.renewable_dispatched_mw.values())
        return {"feasible": total <= 15.0, "min_voltage_pu": 1.0, "max_voltage_pu": 1.0, "max_line_loading_pct": 80.0}

    monkeypatch.setattr(adapter, "get_operating_constraint_snapshot", snapshot)
    result = adapter.apply_heuristic_renewable_curtailment(iterations=10)

    assert result["status"] == "curtailed"
    assert result["dispatch_factor"] == pytest.approx(0.5, abs=0.002)
