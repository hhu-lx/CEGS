import pytest

from src.optimization.mode_capabilities import COMPREHENSIVE_OBJECTIVE_WEIGHTS
from src.optimization.power_dispatch import (
    GeneratorDispatchInput,
    PowerDispatchOptimizer,
    PowerDispatchProblem,
    RenewableForecast,
    StorageDispatchInput,
)


def generator(
    generator_id: str,
    *,
    maximum: float = 100.0,
    initial: float = 0.0,
    ramp: float = 100.0,
    cost: float = 100.0,
    emission: float = 0.5,
) -> GeneratorDispatchInput:
    return GeneratorDispatchInput(
        id=generator_id,
        bus_id=1,
        min_mw=0.0,
        max_mw=maximum,
        initial_mw=initial,
        ramp_up_mw_per_hour=ramp,
        ramp_down_mw_per_hour=ramp,
        cost_linear_yuan_per_mwh=cost,
        cost_quadratic_yuan_per_mw2h=0.0,
        emission_tco2_per_mwh=emission,
    )


def storage(storage_id: str, *, initial: float = 10.0) -> StorageDispatchInput:
    return StorageDispatchInput(
        id=storage_id,
        bus_id=1,
        initial_soc_mwh=initial,
        min_soc_mwh=0.0,
        max_soc_mwh=20.0,
        max_power_mw=10.0,
        charge_efficiency=1.0,
        discharge_efficiency=1.0,
        degradation_cost_per_mwh=0.0,
    )


def test_one_period_balance_bounds_and_dynamic_devices():
    problem = PowerDispatchProblem(
        load_mw=[70.0],
        generators=[generator("g1", maximum=50), generator("g2", maximum=50)],
        renewables=[RenewableForecast("wind", 2, [15.0])],
        storages=[storage("s1"), storage("s2")],
        objective="min_cost",
        horizon_hours=1,
    )

    result = PowerDispatchOptimizer().solve(problem)

    assert result.status == "optimal"
    assert result.strictly_feasible is True
    assert set(result.generator_mw) == {"g1", "g2"}
    assert set(result.storage_power_mw) == {"s1", "s2"}
    supplied = (
        sum(values[0] for values in result.generator_mw.values())
        + result.renewable_dispatched_mw["wind"][0]
        + sum(values[0] for values in result.storage_power_mw.values())
    )
    assert supplied == pytest.approx(70.0, abs=1e-6)
    assert all(0 <= values[0] <= 50 for values in result.generator_mw.values())
    assert all(0 <= values[1] <= 20 for values in result.storage_soc_mwh.values())


def test_fixed_generation_is_balanced_before_external_grid_import():
    result = PowerDispatchOptimizer().solve(PowerDispatchProblem(
        load_mw=[100.0],
        fixed_generation_mw=[60.0],
        renewables=[RenewableForecast("wind", 2, [30.0])],
        external_grid_max_import_mw=50.0,
        objective="min_cost",
        horizon_hours=1,
    ))

    assert result.strictly_feasible is True
    assert result.renewable_dispatched_mw["wind"][0] == pytest.approx(30.0)
    assert result.external_grid_mw[0] == pytest.approx(10.0)


def test_fixed_generation_leaves_only_residual_load_for_renewables():
    result = PowerDispatchOptimizer().solve(PowerDispatchProblem(
        load_mw=[100.0],
        fixed_generation_mw=[80.0],
        renewables=[RenewableForecast("wind", 2, [30.0])],
        external_grid_max_import_mw=20.0,
        external_grid_max_export_mw=0.0,
        objective="min_curtailment",
        horizon_hours=1,
    ))

    assert result.strictly_feasible is True
    assert result.renewable_dispatched_mw["wind"] == pytest.approx([20.0])
    assert result.renewable_curtailed_mw["wind"] == pytest.approx([10.0])
    assert result.external_grid_mw == pytest.approx([0.0])


def test_storage_discharges_before_external_grid_import_when_above_reserve():
    battery = StorageDispatchInput(
        id="battery", bus_id=1, initial_soc_mwh=50.0,
        min_soc_mwh=20.0, max_soc_mwh=60.0, max_power_mw=20.0,
        charge_efficiency=1.0, discharge_efficiency=1.0,
        degradation_cost_per_mwh=2.0,
    )

    result = PowerDispatchOptimizer().solve(PowerDispatchProblem(
        load_mw=[100.0], storages=[battery], external_grid_max_import_mw=100.0,
        objective="min_cost", horizon_hours=1,
    ))

    assert result.storage_power_mw["battery"] == pytest.approx([20.0])
    assert result.external_grid_mw == pytest.approx([80.0])
    assert result.storage_soc_mwh["battery"][-1] == pytest.approx(30.0)


def test_min_cost_with_curtailment_weight_charges_from_renewable_surplus():
    battery = storage("battery", initial=0.0)
    result = PowerDispatchOptimizer().solve(PowerDispatchProblem(
        load_mw=[100.0], fixed_generation_mw=[100.0],
        renewables=[RenewableForecast("wind", 2, [40.0])],
        storages=[battery], objective="min_cost", horizon_hours=1,
        objective_weights={"renewable_curtailment": 100.0},
    ))

    assert result.strictly_feasible is True
    assert result.storage_power_mw["battery"][0] < 0.0
    assert result.renewable_curtailed_mw["wind"][0] > 0.0


def test_terminal_soc_target_prevents_rolling_window_emptying_storage():
    battery = storage("battery", initial=10.0)
    battery = StorageDispatchInput(**{**battery.__dict__, "terminal_soc_mwh": 10.0})
    result = PowerDispatchOptimizer().solve(PowerDispatchProblem(
        load_mw=[100.0], storages=[battery], external_grid_max_import_mw=100.0,
        objective="min_cost", horizon_hours=1,
    ))

    assert result.strictly_feasible is True
    assert result.storage_soc_mwh["battery"][-1] >= 10.0 - 1e-6


def test_rolling_solver_uses_all_fine_grained_periods():
    periods = 24
    result = PowerDispatchOptimizer().solve(PowerDispatchProblem(
        load_mw=[50.0] * periods,
        generators=[generator("g1", maximum=100.0, initial=50.0)],
        horizon_hours=2.0,
        step_hours=5.0 / 60.0,
    ))

    assert len(result.generator_mw["g1"]) == periods
    assert len(result.external_grid_mw) == periods


def test_cost_and_carbon_objectives_choose_different_generators():
    generators = [
        generator("cheap_dirty", cost=10.0, emission=1.0),
        generator("clean_costly", cost=100.0, emission=0.1),
    ]
    base = dict(load_mw=[50.0], generators=generators, horizon_hours=1)

    cost = PowerDispatchOptimizer().solve(PowerDispatchProblem(**base, objective="min_cost"))
    carbon = PowerDispatchOptimizer().solve(PowerDispatchProblem(**base, objective="min_carbon"))

    assert cost.generator_mw["cheap_dirty"][0] == pytest.approx(50.0)
    assert cost.generator_mw["clean_costly"][0] == pytest.approx(0.0)
    assert carbon.generator_mw["clean_costly"][0] == pytest.approx(50.0)
    assert carbon.generator_mw["cheap_dirty"][0] == pytest.approx(0.0)


def test_min_curtailment_uses_more_renewable_than_min_cost_with_must_run_unit():
    thermal = GeneratorDispatchInput(
        id="must_run", bus_id=1, min_mw=30.0, max_mw=100.0, initial_mw=30.0,
        ramp_up_mw_per_hour=100.0, ramp_down_mw_per_hour=100.0,
        cost_linear_yuan_per_mwh=-10.0, cost_quadratic_yuan_per_mw2h=0.0,
        emission_tco2_per_mwh=0.8,
    )
    kwargs = dict(
        load_mw=[60.0], generators=[thermal],
        renewables=[RenewableForecast("pv", 2, [40.0])], horizon_hours=1,
    )

    cost = PowerDispatchOptimizer().solve(PowerDispatchProblem(**kwargs, objective="min_cost"))
    green = PowerDispatchOptimizer().solve(PowerDispatchProblem(**kwargs, objective="min_curtailment"))

    assert green.renewable_dispatched_mw["pv"][0] > cost.renewable_dispatched_mw["pv"][0]
    assert green.renewable_curtailed_mw["pv"][0] == pytest.approx(10.0)


def test_peak_shaving_charges_before_peak_and_discharges_at_peak():
    result = PowerDispatchOptimizer().solve(PowerDispatchProblem(
        load_mw=[10.0, 10.0, 30.0],
        generators=[generator("grid", maximum=50.0)],
        storages=[storage("battery", initial=0.0)],
        objective="peak_shaving",
        horizon_hours=3,
    ))

    power = result.storage_power_mw["battery"]
    assert any(value < -1e-6 for value in power[:2])
    assert power[2] > 1e-6
    assert max(result.generator_mw["grid"]) < 30.0


def test_weighted_peak_shaving_is_not_diluted_by_large_constant_base_load():
    battery = StorageDispatchInput(
        id="battery", bus_id=1, initial_soc_mwh=50.0,
        min_soc_mwh=10.0, max_soc_mwh=100.0, max_power_mw=25.0,
        charge_efficiency=0.95, discharge_efficiency=0.95,
        degradation_cost_per_mwh=2.0,
    )
    result = PowerDispatchOptimizer().solve(PowerDispatchProblem(
        load_mw=[6300.0, 6314.0, 6294.0],
        generators=[generator(
            "grid", maximum=7000.0, initial=6300.0,
            ramp=7000.0, cost=100.0,
        )],
        storages=[battery],
        electricity_prices=[0.626, 0.6263, 0.6259],
        objective="weighted",
        objective_weights=dict(COMPREHENSIVE_OBJECTIVE_WEIGHTS),
        horizon_hours=3,
        external_grid_max_import_mw=1000.0,
    ))

    schedule = result.storage_power_mw["battery"]
    assert any(value < -1e-6 for value in schedule)
    assert any(value > 1e-6 for value in schedule)


def test_time_of_use_prices_shift_storage_from_cheap_to_expensive_period():
    result = PowerDispatchOptimizer().solve(PowerDispatchProblem(
        load_mw=[20.0, 20.0],
        generators=[generator("grid", maximum=50.0, cost=100.0)],
        storages=[storage("battery", initial=0.0)],
        electricity_prices=[0.2, 1.2],
        objective="min_cost",
        horizon_hours=2,
    ))

    assert result.storage_power_mw["battery"][0] < -1e-6
    assert result.storage_power_mw["battery"][1] > 1e-6


def test_absolute_tariff_level_remains_visible_in_cost_accounting():
    base = dict(
        load_mw=[20.0], generators=[generator("grid", maximum=50.0, cost=100.0)],
        objective="min_cost", horizon_hours=1,
    )
    low = PowerDispatchOptimizer().solve(PowerDispatchProblem(
        **base, electricity_prices=[0.2]
    ))
    high = PowerDispatchOptimizer().solve(PowerDispatchProblem(
        **base, electricity_prices=[9.0]
    ))

    assert high.objective_components["cost"]["raw"] > low.objective_components["cost"]["raw"]


def test_first_period_ramp_uses_real_control_interval_and_grid_balances_gap():
    result = PowerDispatchOptimizer().solve(PowerDispatchProblem(
        load_mw=[10.0],
        generators=[generator("slow", maximum=50.0, initial=0.0, ramp=3600.0)],
        objective="min_cost", horizon_hours=1,
        control_interval_hours=1.0 / 3600.0,
        external_grid_max_import_mw=100.0,
    ))

    assert result.generator_mw["slow"][0] == pytest.approx(1.0, abs=1e-6)
    assert result.external_grid_mw[0] >= 9.0 - 1e-6


def test_short_forecast_is_cyclically_expanded_to_24_periods():
    result = PowerDispatchOptimizer().solve(PowerDispatchProblem(
        load_mw=[20.0, 30.0, 25.0],
        generators=[generator("g", maximum=60.0)],
        renewables=[RenewableForecast("wind", 2, [1.0, 2.0, 3.0])],
        objective="min_cost",
    ))

    assert result.forecast_fill == "cyclic"
    assert len(result.generator_mw["g"]) == 24
    assert result.renewable_dispatched_mw["wind"][0:6] == pytest.approx([1, 2, 3, 1, 2, 3])


def test_ramp_constraint_binds_between_periods():
    result = PowerDispatchOptimizer().solve(PowerDispatchProblem(
        load_mw=[10.0, 40.0],
        generators=[
            generator("slow", maximum=100.0, initial=10.0, ramp=10.0, cost=10.0),
            generator("fast", maximum=100.0, initial=0.0, ramp=100.0, cost=100.0),
        ],
        objective="min_cost",
        horizon_hours=2,
    ))

    output = result.generator_mw["slow"]
    assert output == pytest.approx([10.0, 20.0])
    assert result.generator_mw["fast"][1] == pytest.approx(20.0)
    assert result.strictly_feasible is True

