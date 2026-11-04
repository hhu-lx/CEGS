import pytest

from src.domain.datacenter import DataCenter
from src.domain.device import DeviceSpec
from src.domain.task import Task
from src.optimization.joint_coordination import JointCoordinationOptimizer
from src.optimization.mode_capabilities import COMPREHENSIVE_OBJECTIVE_WEIGHTS


def test_comprehensive_defaults_prioritize_peak_shaving_over_curtailment():
    assert COMPREHENSIVE_OBJECTIVE_WEIGHTS["peak_shaving"] == 3.0
    assert COMPREHENSIVE_OBJECTIVE_WEIGHTS["renewable_curtailment"] == 1.0
    assert COMPREHENSIVE_OBJECTIVE_WEIGHTS["storage_degradation"] == 0.5
from src.optimization.power_dispatch import (
    GeneratorDispatchInput,
    PowerDispatchProblem,
    RenewableForecast,
    StorageDispatchInput,
)


def power_problem(*, renewable_bus=2, horizon=1, start_second=0):
    return PowerDispatchProblem(
        load_mw=[10.0] * horizon,
        generators=[
            GeneratorDispatchInput(
                id="g1", bus_id=1, min_mw=0, max_mw=100, initial_mw=10,
                ramp_up_mw_per_hour=100, ramp_down_mw_per_hour=100,
                cost_linear_yuan_per_mwh=100,
                cost_quadratic_yuan_per_mw2h=0, emission_tco2_per_mwh=0.5,
            )
        ],
        renewables=[RenewableForecast("wind", renewable_bus, [20.0] * horizon)],
        storages=[StorageDispatchInput(
            id="s", bus_id=1, initial_soc_mwh=5, min_soc_mwh=0,
            max_soc_mwh=10, max_power_mw=3,
            charge_efficiency=1, discharge_efficiency=1,
        )],
        objective="min_cost", horizon_hours=horizon, start_second=start_second,
    )


def task(task_id="t", **kwargs):
    values = {
        "id": task_id, "user_id": "u", "task_type": "general",
        "required_compute": 20, "duration_hours": 1, "max_wait_seconds": 7200,
    }
    values.update(kwargs)
    return Task(**values)


def centers():
    return [
        DataCenter(id="dc1", name="dc1", grid_bus_id=1, total_compute=100, power_per_tflops=0.01),
        DataCenter(id="dc2", name="dc2", grid_bus_id=2, total_compute=100, power_per_tflops=0.01),
    ]


def test_joint_model_places_compute_at_bus_with_available_renewable_power():
    result = JointCoordinationOptimizer().solve(
        [task()], centers(), power_problem(renewable_bus=2),
        objective="min_cost", weights={}, latency_ms={}, carbon_intensity={},
    )

    assert result.status == "optimal"
    assert result.strictly_feasible is True
    assert result.assignments == {"t": "dc2"}
    assert result.renewable_dispatched_mw["wind"][0] > 0
    supplied = (
        sum(values[0] for values in result.generator_mw.values())
        + result.renewable_dispatched_mw["wind"][0]
        + sum(values[0] for values in result.storage_power_mw.values())
    )
    task_power = centers()[1].power_for_task_mw(task())
    assert supplied == pytest.approx(10.0 + task_power)


def test_joint_model_balances_fixed_generation_before_grid_import():
    """The global model must include the data-driven conventional plan."""
    problem = PowerDispatchProblem(
        load_mw=[100.0],
        fixed_generation_mw=[60.0],
        renewables=[RenewableForecast("wind", 2, [30.0])],
        external_grid_max_import_mw=20.0,
        objective="min_cost",
        horizon_hours=1,
    )

    result = JointCoordinationOptimizer().solve(
        [], [], problem, objective="min_cost", weights={}, latency_ms={}, carbon_intensity={},
    )

    assert result.strictly_feasible is True
    assert result.renewable_dispatched_mw["wind"] == pytest.approx([30.0])
    assert result.external_grid_mw == pytest.approx([10.0])


def test_joint_model_curtails_renewable_surplus_above_fixed_plan_residual():
    problem = PowerDispatchProblem(
        load_mw=[100.0],
        fixed_generation_mw=[80.0],
        renewables=[RenewableForecast("wind", 2, [30.0])],
        external_grid_max_import_mw=20.0,
        external_grid_max_export_mw=0.0,
        objective="min_curtailment",
        horizon_hours=1,
    )

    result = JointCoordinationOptimizer().solve(
        [], [], problem, objective="min_curtailment", weights={}, latency_ms={}, carbon_intensity={},
    )

    assert result.strictly_feasible is True
    assert result.renewable_dispatched_mw["wind"] == pytest.approx([20.0])
    assert result.renewable_curtailed_mw["wind"] == pytest.approx([10.0])
    assert result.external_grid_mw == pytest.approx([0.0])


def test_joint_model_discharges_storage_before_external_grid_import():
    battery = StorageDispatchInput(
        id="battery", bus_id=1, initial_soc_mwh=50.0,
        min_soc_mwh=20.0, max_soc_mwh=60.0, max_power_mw=20.0,
        charge_efficiency=1.0, discharge_efficiency=1.0,
        degradation_cost_per_mwh=2.0,
    )
    result = JointCoordinationOptimizer().solve(
        [], [], PowerDispatchProblem(
            load_mw=[100.0], storages=[battery], external_grid_max_import_mw=100.0,
            objective="min_cost", horizon_hours=1,
        ), objective="min_cost", weights={}, latency_ms={}, carbon_intensity={},
    )

    assert result.storage_power_mw["battery"] == pytest.approx([4.0])
    assert result.external_grid_mw == pytest.approx([96.0])
    assert result.storage_soc_mwh["battery"][-1] == pytest.approx(46.0)


def test_joint_model_absorbs_generation_surplus_with_storage():
    battery = StorageDispatchInput(
        id="battery", bus_id=1, initial_soc_mwh=50.0,
        min_soc_mwh=10.0, max_soc_mwh=100.0, max_power_mw=25.0,
        charge_efficiency=1.0, discharge_efficiency=1.0,
    )
    result = JointCoordinationOptimizer().solve(
        [], [], PowerDispatchProblem(
            load_mw=[100.0], fixed_generation_mw=[130.0], storages=[battery],
            external_grid_max_import_mw=100.0, external_grid_max_export_mw=100.0,
            objective="weighted", horizon_hours=1,
        ), objective="weighted", weights={"peak_shaving": 3.0},
        latency_ms={}, carbon_intensity={},
    )

    assert result.storage_power_mw["battery"][0] < 0.0
    assert "supply_balance" in result.objective_components


def test_joint_model_uses_available_green_surplus_for_charge_direction():
    battery = StorageDispatchInput(
        id="battery", bus_id=1, initial_soc_mwh=10.0,
        min_soc_mwh=10.0, max_soc_mwh=100.0, max_power_mw=25.0,
        charge_efficiency=1.0, discharge_efficiency=1.0,
    )
    result = JointCoordinationOptimizer().solve(
        [], [], PowerDispatchProblem(
            load_mw=[100.0], fixed_generation_mw=[0.0],
            renewables=[RenewableForecast("wind", 1, [130.0])],
            storages=[battery], external_grid_max_export_mw=100.0,
            objective="weighted", horizon_hours=1,
        ), objective="weighted", weights={"peak_shaving": 3.0},
        latency_ms={}, carbon_intensity={},
    )

    assert result.storage_power_mw["battery"][0] < 0.0


def test_joint_model_allows_first_period_storage_direction_reversal():
    """A rolling solve must remain feasible when surplus follows discharge."""
    battery = StorageDispatchInput(
        id="battery", bus_id=1, initial_soc_mwh=50.0,
        min_soc_mwh=10.0, max_soc_mwh=100.0, max_power_mw=20.0,
        charge_efficiency=1.0, discharge_efficiency=1.0,
        initial_power_mw=20.0,
    )
    result = JointCoordinationOptimizer().solve(
        [], [], PowerDispatchProblem(
            load_mw=[10.0],
            renewables=[RenewableForecast("wind", 1, [20.0])],
            storages=[battery], external_grid_max_import_mw=100.0,
            objective="min_cost", horizon_hours=1,
        ), objective="min_cost", weights={}, latency_ms={}, carbon_intensity={},
    )

    assert result.strictly_feasible is True
    assert result.storage_power_mw["battery"][0] <= 0.0


def test_joint_model_never_charges_from_conventional_generation_without_green_surplus():
    generator = GeneratorDispatchInput(
        id="grid", bus_id=1, min_mw=0.0, max_mw=200.0, initial_mw=100.0,
        ramp_up_mw_per_hour=200.0, ramp_down_mw_per_hour=200.0,
        cost_linear_yuan_per_mwh=100.0, cost_quadratic_yuan_per_mw2h=0.0,
        emission_tco2_per_mwh=0.5,
    )
    battery = StorageDispatchInput(
        id="battery", bus_id=1, initial_soc_mwh=10.0,
        min_soc_mwh=0.0, max_soc_mwh=100.0, max_power_mw=25.0,
        charge_efficiency=1.0, discharge_efficiency=1.0,
    )
    result = JointCoordinationOptimizer().solve(
        [], [], PowerDispatchProblem(
            load_mw=[100.0], generators=[generator], storages=[battery],
            external_grid_max_import_mw=100.0, objective="weighted",
            horizon_hours=1,
        ), objective="weighted", weights={"peak_shaving": 0.0},
        latency_ms={}, carbon_intensity={},
    )

    assert result.storage_power_mw["battery"][0] >= -1e-6


def test_joint_model_keeps_full_storage_idle_during_green_surplus():
    battery = StorageDispatchInput(
        id="battery", bus_id=1, initial_soc_mwh=100.0,
        min_soc_mwh=10.0, max_soc_mwh=100.0, max_power_mw=25.0,
        charge_efficiency=1.0, discharge_efficiency=1.0,
    )
    result = JointCoordinationOptimizer().solve(
        [], [], PowerDispatchProblem(
            load_mw=[100.0],
            renewables=[RenewableForecast("wind", 1, [130.0])],
            storages=[battery], external_grid_max_export_mw=100.0,
            objective="weighted", horizon_hours=1,
        ), objective="weighted", weights={"peak_shaving": 3.0},
        latency_ms={}, carbon_intensity={}, maintain_terminal_soc=True,
    )

    assert result.strictly_feasible is True
    assert result.storage_power_mw["battery"][0] == pytest.approx(0.0)


def test_joint_model_does_not_force_storage_cycling_for_costly_surplus():
    """High degradation cost must not create an artificial charge/discharge cycle."""
    battery = StorageDispatchInput(
        id="battery", bus_id=1, initial_soc_mwh=10.0,
        min_soc_mwh=0.0, max_soc_mwh=100.0, max_power_mw=25.0,
        charge_efficiency=1.0, discharge_efficiency=1.0,
        degradation_cost_per_mwh=10.0,
    )
    result = JointCoordinationOptimizer().solve(
        [], [], PowerDispatchProblem(
            load_mw=[100.0, 100.0], fixed_generation_mw=[100.0, 0.0],
            renewables=[RenewableForecast("wind", 99, [10.0, 0.0])],
            storages=[battery], external_grid_max_import_mw=100.0,
            external_grid_max_export_mw=0.0, objective="weighted", horizon_hours=2,
        ), objective="weighted", weights={"peak_shaving": 0.0},
        latency_ms={}, carbon_intensity={},
    )

    assert result.storage_power_mw["battery"][0] == pytest.approx(0.0)
    assert result.renewable_curtailed_mw["wind"][0] == pytest.approx(10.0)


def test_joint_soft_load_balance_splits_equal_cost_batch():
    tasks = [task(str(index), required_compute=20) for index in range(4)]

    result = JointCoordinationOptimizer().solve(
        tasks, centers(), power_problem(renewable_bus=1),
        objective="min_cost", weights={}, latency_ms={}, carbon_intensity={},
        load_balance_weight=1.0,
    )

    assert result.status == "optimal"
    assert sum(center_id == "dc1" for center_id in result.assignments.values()) == 2
    assert sum(center_id == "dc2" for center_id in result.assignments.values()) == 2


def test_joint_min_curtailment_keeps_the_same_center_balance_as_comprehensive_mode():
    tasks = [task(str(index), required_compute=20) for index in range(4)]

    result = JointCoordinationOptimizer().solve(
        tasks, centers(), power_problem(renewable_bus=1),
        objective="min_curtailment", weights={}, latency_ms={}, carbon_intensity={},
        load_balance_weight=1.0,
    )

    assert result.status == "optimal"
    assert sum(center_id == "dc1" for center_id in result.assignments.values()) == 2
    assert sum(center_id == "dc2" for center_id in result.assignments.values()) == 2


def test_joint_activity_floor_uses_every_eligible_center_despite_cost_preference():
    unequal_centers = [
        DataCenter(id="a", name="a", grid_bus_id=1, total_compute=100, power_per_tflops=0.01),
        DataCenter(id="b", name="b", grid_bus_id=2, total_compute=100, power_per_tflops=0.10),
        DataCenter(id="c", name="c", grid_bus_id=3, total_compute=100, power_per_tflops=0.20),
    ]
    tasks = [task(f"t-{index}", required_compute=10) for index in range(5)]

    result = JointCoordinationOptimizer().solve(
        tasks, unequal_centers, power_problem(renewable_bus=1),
        objective="min_cost", weights={}, latency_ms={}, carbon_intensity={},
        minimum_active_center_tasks=1,
    )

    assert result.status == "optimal"
    assert set(result.assignments.values()) == {"a", "b", "c"}


def test_joint_activity_floor_exempts_centers_without_eligible_task():
    three_centers = centers() + [
        DataCenter(id="dc3", name="dc3", grid_bus_id=3, total_compute=100, power_per_tflops=0.01)
    ]
    tasks = [
        task("a", user_specified_data_center="dc1"),
        task("b", user_specified_data_center="dc2"),
        task("c", user_specified_data_center="dc1"),
    ]

    result = JointCoordinationOptimizer().solve(
        tasks, three_centers, power_problem(renewable_bus=1),
        objective="min_cost", weights={}, latency_ms={}, carbon_intensity={},
        minimum_active_center_tasks=1,
    )

    assert result.status == "optimal"
    assert set(result.assignments.values()) == {"dc1", "dc2"}


def test_joint_activity_floor_exempts_center_that_cannot_fit_any_task():
    constrained_centers = centers() + [
        DataCenter(id="small", name="small", grid_bus_id=3, total_compute=10, power_per_tflops=0.01)
    ]
    tasks = [task(f"t-{index}", required_compute=20) for index in range(3)]

    result = JointCoordinationOptimizer().solve(
        tasks, constrained_centers, power_problem(renewable_bus=1),
        objective="min_cost", weights={}, latency_ms={}, carbon_intensity={},
        minimum_active_center_tasks=1,
    )

    assert result.status == "optimal"
    assert "small" not in result.assignments.values()


def test_green_lexicographic_tie_break_never_sacrifices_minimum_cost():
    unequal_centers = [
        DataCenter(id="efficient", name="efficient", grid_bus_id=1, total_compute=100, power_per_tflops=0.01),
        DataCenter(id="green_but_costly", name="green", grid_bus_id=2, total_compute=100, power_per_tflops=0.1),
    ]
    problem = power_problem(renewable_bus=2)
    problem = PowerDispatchProblem(
        **{**problem.__dict__, "renewables": [RenewableForecast("wind", 2, [0.5])]}
    )

    result = JointCoordinationOptimizer().solve(
        [task(required_compute=10)], unequal_centers, problem,
        objective="min_cost", weights={}, latency_ms={}, carbon_intensity={},
    )

    assert result.assignments == {"t": "efficient"}


def test_joint_model_enforces_resources_submission_and_wait_window():
    gpu_center = DataCenter(
        id="gpu", name="gpu", grid_bus_id=1, total_compute=50,
        total_bandwidth=100, power_per_tflops=0.01,
        device_pool=[DeviceSpec(
            model="GPU-H100", equipment_type="compute", quantity=1,
            compute_tflops=80, rated_power_kw=0.7,
        )],
    )
    delayed = task("delayed", submitted_at=3600, required_bandwidth_mbps=20)
    impossible = task(
        "impossible", submitted_at=0, required_compute=40,
        required_bandwidth_mbps=200, required_gpu_count=2,
    )

    result = JointCoordinationOptimizer().solve(
        [delayed, impossible], [gpu_center],
        power_problem(renewable_bus=1, horizon=3, start_second=0),
        objective="weighted", weights={"cost": 1, "delay": 1},
        latency_ms={}, carbon_intensity={},
    )

    assert result.assignments == {"delayed": "gpu"}
    assert result.start_periods["delayed"] >= 1
    assert "impossible" in result.queued_tasks


def test_joint_model_supports_dynamic_data_center_count():
    dynamic_centers = centers() + [
        DataCenter(id="dc3", name="dc3", grid_bus_id=3, total_compute=100, power_per_tflops=0.02)
    ]
    result = JointCoordinationOptimizer().solve(
        [task("a"), task("b")], dynamic_centers, power_problem(),
        objective="min_delay", weights={},
        latency_ms={("region_a", "region_a"): 5.0}, carbon_intensity={},
    )

    assert set(result.assignments) == {"a", "b"}
    assert set(result.assignments.values()).issubset({"dc1", "dc2", "dc3"})


def test_joint_weighted_peak_shaving_cannot_be_bypassed_by_grid_import():
    problem = PowerDispatchProblem(
        load_mw=[6300.0, 6314.0, 6294.0],
        generators=[GeneratorDispatchInput(
            id="grid", bus_id=1, min_mw=0.0, max_mw=7000.0,
            initial_mw=6300.0, ramp_up_mw_per_hour=7000.0,
            ramp_down_mw_per_hour=7000.0,
            cost_linear_yuan_per_mwh=100.0,
            cost_quadratic_yuan_per_mw2h=0.0,
            emission_tco2_per_mwh=0.5,
        )],
        storages=[StorageDispatchInput(
            id="battery", bus_id=1, initial_soc_mwh=50.0,
            min_soc_mwh=10.0, max_soc_mwh=100.0, max_power_mw=25.0,
            charge_efficiency=0.95, discharge_efficiency=0.95,
            degradation_cost_per_mwh=2.0,
        )],
        electricity_prices=[0.626, 0.6263, 0.6259],
        objective="weighted",
        objective_weights=dict(COMPREHENSIVE_OBJECTIVE_WEIGHTS),
        horizon_hours=3,
        external_grid_max_import_mw=1000.0,
    )

    result = JointCoordinationOptimizer().solve(
        [], centers(), problem,
        objective="weighted",
        weights=dict(COMPREHENSIVE_OBJECTIVE_WEIGHTS),
        latency_ms={}, carbon_intensity={},
    )

    schedule = result.storage_power_mw["battery"]
    assert all(abs(value) <= 25.0 for value in schedule)
    ramp_limit = 25.0 * 0.20
    assert all(
        abs(schedule[index] - schedule[index - 1]) <= ramp_limit + 1e-6
        for index in range(1, len(schedule))
    )


def test_green_tie_break_preserves_weighted_storage_plan_without_tasks():
    load = [
        6307.22, 6310.58, 6314.23, 6312.35, 6310.55, 6310.31,
        6307.46, 6303.97, 6300.85, 6298.52, 6296.03, 6295.14,
        6293.84, 6294.86, 6296.32, 6300.28, 6307.17, 6311.72,
        6313.70, 6315.40, 6312.84, 6310.56, 6310.62, 6309.83,
    ]
    renewable = [
        6400.00, 202.15, 177.84, 150.93, 136.11, 164.32,
        165.10, 164.97, 156.26, 132.86, 144.04, 153.40,
        153.40, 164.97, 196.30, 308.75, 426.66, 630.50,
        773.89, 877.24, 886.47, 889.59, 813.02, 763.10,
    ]
    problem = PowerDispatchProblem(
        load_mw=load,
        generators=[GeneratorDispatchInput(
            id="grid", bus_id=1, min_mw=0.0, max_mw=7000.0,
            initial_mw=6300.0, ramp_up_mw_per_hour=7000.0,
            ramp_down_mw_per_hour=7000.0,
            cost_linear_yuan_per_mwh=100.0,
            cost_quadratic_yuan_per_mw2h=0.0,
            emission_tco2_per_mwh=0.5,
        )],
        renewables=[RenewableForecast("wind", 2, renewable)],
        storages=[StorageDispatchInput(
            id="battery", bus_id=1, initial_soc_mwh=50.0,
            min_soc_mwh=10.0, max_soc_mwh=100.0, max_power_mw=25.0,
            charge_efficiency=0.95, discharge_efficiency=0.95,
            degradation_cost_per_mwh=2.0,
        )],
        electricity_prices=[
            0.5 + (demand - green) / 1000.0 * 0.02
            for demand, green in zip(load, renewable)
        ],
        objective="weighted",
        objective_weights=dict(COMPREHENSIVE_OBJECTIVE_WEIGHTS),
        horizon_hours=24,
    )

    result = JointCoordinationOptimizer().solve(
        [], centers(), problem,
        objective="weighted",
        weights=dict(COMPREHENSIVE_OBJECTIVE_WEIGHTS),
        latency_ms={}, carbon_intensity={},
    )

    # System-level renewable surplus is absorbed immediately, subject to the
    # first-period 20% ramp limit.
    assert result.storage_power_mw["battery"][0] >= -1e-6


def test_joint_model_retries_ac_validation_and_only_applies_successful_result():
    validations = []
    applied = []
    restored = []

    def validate(candidate, attempt):
        validations.append(attempt)
        return attempt == 2

    optimizer = JointCoordinationOptimizer(
        ac_validator=validate,
        result_applier=lambda candidate: applied.append(candidate),
        feasible_restorer=lambda: restored.append(True),
    )
    result = optimizer.solve(
        [task()], centers(), power_problem(), objective="min_cost",
        weights={}, latency_ms={}, carbon_intensity={},
    )

    assert result.status == "optimal"
    assert validations == [1, 2]
    assert applied == [result]
    assert restored == []


def test_joint_model_restores_previous_point_when_both_ac_attempts_fail():
    applied = []
    restored = []
    optimizer = JointCoordinationOptimizer(
        ac_validator=lambda candidate, attempt: False,
        result_applier=lambda candidate: applied.append(candidate),
        feasible_restorer=lambda: restored.append(True),
    )

    result = optimizer.solve(
        [task()], centers(), power_problem(), objective="min_cost",
        weights={}, latency_ms={}, carbon_intensity={},
    )

    assert result.status == "ac_validation_failed"
    assert result.strictly_feasible is False
    assert applied == []
    assert restored == [True]

