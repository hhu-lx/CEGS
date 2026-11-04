from src.domain.datacenter import DataCenter
from src.domain.device import DeviceSpec
from src.domain.enums import TaskStatus
from src.domain.task import Task
from src.simulation.engine import SimulationEngine
from src.simulation.scheduler import Scheduler
from src.strategies.allocation.lowest_price import LowestPriceStrategy
from src.optimization.power_dispatch import (
    GeneratorDispatchInput,
    PowerDispatchProblem,
    RenewableForecast,
    StorageDispatchInput,
)
from src.optimization.local_coordination import LocalCoordinationResult
from src.optimization.joint_coordination import JointCoordinationResult
from src.strategies.electricity.marginal import MarginalElectricityPricing
import simpy
import pytest


def test_engine_optimization_cache_is_bounded_and_returns_defensive_copies():
    engine = object.__new__(SimulationEngine)
    engine._optimization_cache_put(("a",), {"nested": {"value": 1}})
    cached = engine._optimization_cache_get(("a",))
    cached["nested"]["value"] = 99
    assert engine._optimization_cache_get(("a",))["nested"]["value"] == 1

    for index in range(40):
        engine._optimization_cache_put((index,), {"value": index})
    assert engine._optimization_cache_get(("a",)) is None


def test_engine_optimization_cache_version_invalidates_entries():
    engine = object.__new__(SimulationEngine)
    engine._optimization_cache_put(("same",), {"status": "optimal"})
    assert engine._optimization_cache_get(("same",)) == {"status": "optimal"}
    engine._bump_state_version("test")
    assert engine._optimization_cache_get(("same",)) is None


def test_engine_reuses_strictly_feasible_coordination_result_for_same_batch():
    engine = object.__new__(SimulationEngine)
    engine.optimization_config = {"mode": "hierarchical"}
    engine.current_second = 10
    engine._optimization_state_version = 0
    calls = []
    engine._run_local_coordination = lambda tasks: calls.append(tasks) or {
        "status": "optimal", "strictly_feasible": True, "assignments": {"t": "dc"}
    }
    engine.pp_adapter = type("Adapter", (), {"build_power_dispatch_problem": lambda self: None})()
    task = Task(user_id="u", task_type="general", compute_amount_tflop_hours=1, duration_hours=1)
    task.id = "t"
    first = engine.optimize_ready_tasks([task])
    second = engine.optimize_ready_tasks([task])
    assert first == second
    assert len(calls) == 1


def test_engine_persists_copt_task_assignment_result():
    engine = object.__new__(SimulationEngine)
    task = Task(user_id="u", task_type="general", compute_amount_tflop_hours=1, duration_hours=1)
    task.transition_to(TaskStatus.SCHEDULING)
    engine.data_centers = [DataCenter(id="dc", name="dc", total_compute=10)]

    result = engine.optimize_ready_tasks([task])

    assert result["status"] == "optimal"
    assert result["assignments"] == {task.id: "dc"}
    assert engine.get_optimization_result() == result


def test_engine_can_disable_copt_and_leave_tasks_to_scheduler():
    engine = object.__new__(SimulationEngine)
    engine.optimization_config = {"enabled": False}

    result = engine.optimize_ready_tasks([])

    assert result == {"status": "disabled", "objective_value": None, "assignments": {}}


class _FakeSim:
    def run_task(self, task):
        yield 0


def _dispatch_engine(mode):
    engine = object.__new__(SimulationEngine)
    engine.env = simpy.Environment()
    engine.ready_tasks = []
    engine.dispatched_task_ids = set()
    engine.optimization_config = {"mode": mode, "forecast_step_minutes": 5.0}
    engine.data_centers = [DataCenter(id="dc-a", name="a", total_compute=10), DataCenter(id="dc-b", name="b", total_compute=10)]
    engine.dc_sims = {"dc-a": _FakeSim(), "dc-b": _FakeSim()}
    engine.scheduler = type("Scheduler", (), {"select_data_center": lambda self, task, dcs: dcs[0]})()
    return engine


def test_dispatch_mode_none_uses_scheduler_without_optimizer():
    engine = _dispatch_engine("none")
    task = Task(user_id="u", task_type="general", compute_amount_tflop_hours=1, duration_hours=1)
    task.transition_to(TaskStatus.SCHEDULING)
    engine.ready_tasks = [task]
    called = []
    engine.optimize_ready_tasks = lambda tasks: called.append(tasks)

    engine._dispatch_ready_tasks()

    assert called == []
    assert task.allocated_data_center_id == "dc-a"


def test_heuristic_selection_uses_selected_dispatch_strategy():
    engine = object.__new__(SimulationEngine)
    engine.optimization_config = {"mode": "none"}
    price_favoured = DataCenter(
        id="cheap", name="cheap", total_compute=100,
        used_compute=80, current_price=0.1,
    )
    resource_favoured = DataCenter(
        id="available", name="available", total_compute=100,
        used_compute=10, current_price=1.0,
    )
    engine.data_centers = [price_favoured, resource_favoured]
    engine.scheduler = Scheduler(LowestPriceStrategy())
    task = Task(user_id="u", task_type="general", required_compute=5, duration_hours=1)

    selected = engine._select_data_center(task, engine.data_centers)

    assert selected.id == "cheap"


def test_heuristic_assignments_follow_selected_price_strategy():
    task = Task(user_id="u", task_type="general", required_compute=5, duration_hours=1)

    def selected(prices, carbon):
        engine = object.__new__(SimulationEngine)
        engine.optimization_config = {"mode": "none"}
        engine.data_centers = [
            DataCenter(id="a", name="a", total_compute=100, used_compute=40, current_price=prices[0], grid_bus_id=1),
            DataCenter(id="b", name="b", total_compute=100, used_compute=10, current_price=prices[1], grid_bus_id=2),
        ]
        engine.pp_adapter = type("Grid", (), {"get_bus_carbon_intensity": lambda self, bus: carbon[bus]})()
        engine.scheduler = Scheduler(LowestPriceStrategy())
        return engine._select_data_center(task, engine.data_centers).id

    assert selected((0.1, 2.0), {1: 0.1, 2: 0.9}) == "a"
    assert selected((3.0, 0.1), {1: 0.9, 2: 0.1}) == "b"


class _PowerAdapter:
    def __init__(self, ac_feasible=True):
        self.ac_feasible = ac_feasible
        self.applied = None
        self.restored = False
        self.problem_kwargs = None

    def build_power_dispatch_problem(self, second, horizon_hours=24, **kwargs):
        self.problem_kwargs = {"horizon_hours": horizon_hours, **kwargs}
        return PowerDispatchProblem(
            load_mw=[40.0, 60.0],
            generators=[GeneratorDispatchInput(
                id="thermal", bus_id=1, min_mw=0.0, max_mw=100.0,
                initial_mw=30.0, ramp_up_mw_per_hour=100.0,
                ramp_down_mw_per_hour=100.0, cost_linear_yuan_per_mwh=100.0,
                cost_quadratic_yuan_per_mw2h=0.0, emission_tco2_per_mwh=0.5,
            )],
            renewables=[RenewableForecast("wind", 2, [10.0, 20.0])],
            storages=[StorageDispatchInput(
                id="battery", bus_id=1, initial_soc_mwh=5.0, min_soc_mwh=0.0,
                max_soc_mwh=10.0, max_power_mw=5.0,
                charge_efficiency=1.0, discharge_efficiency=1.0,
            )],
            objective=kwargs.get("objective", "min_cost"),
            objective_weights=kwargs.get("objective_weights", {}),
            horizon_hours=2,
        )

    def apply_power_dispatch(self, result, period=0):
        self.applied = result
        return {"dispatch_id": "dispatch-1"}

    def validate_dispatch_ac(self):
        return {"feasible": self.ac_feasible, "dispatch_id": "dispatch-1"}

    def restore_last_feasible_dispatch(self):
        self.restored = True
        return True

    def get_bus_carbon_intensity(self, bus_id):
        return 0.5


def test_ac_validation_uses_candidate_per_bus_compute_load_then_restores_live_load():
    engine = object.__new__(SimulationEngine)
    task = Task(user_id="u", task_type="general", required_compute=10, duration_hours=1)
    center = DataCenter(
        id="dc", name="dc", grid_bus_id=3, total_compute=100,
        power_per_tflops=0.01,
    )
    engine.data_centers = [center]
    engine.dc_sims = {
        "dc": type("Sim", (), {"current_load_mw": 2.0})()
    }
    observed = []

    class Grid(_PowerAdapter):
        def __init__(self):
            super().__init__()
            self.extra_loads = {3: 2.0}

        def replace_compute_loads(self, loads):
            self.extra_loads = dict(loads)

        def validate_dispatch_ac(self):
            observed.append(dict(self.extra_loads))
            return {"feasible": True}

    engine.pp_adapter = Grid()
    problem = engine.pp_adapter.build_power_dispatch_problem(0, horizon_hours=2)
    power = __import__("src.optimization.power_dispatch", fromlist=["PowerDispatchOptimizer"]).PowerDispatchOptimizer().solve(problem)

    engine._validate_candidate_ac(power, {task.id: "dc"}, {task.id: task})

    assert observed == [{3: pytest.approx(2.0 + center.power_for_task_mw(task))}]
    assert engine.pp_adapter.extra_loads == {3: 2.0}


def test_marginal_price_forecast_tracks_each_rolling_load_period():
    engine = object.__new__(SimulationEngine)
    engine.fixed_pricing = None
    engine.data_centers = []
    engine.pp_adapter = type(
        "Grid",
        (),
        {
            "electricity_strategy": MarginalElectricityPricing(
                base_price=0.5, sensitivity=0.02, scale=1000.0
            ),
            "get_bus_marginal_price": lambda self, bus: 0.5,
        },
    )()
    problem = PowerDispatchProblem(
        load_mw=[100.0, 900.0],
        generators=[GeneratorDispatchInput(
            id="g", bus_id=1, min_mw=0.0, max_mw=1000.0,
            initial_mw=100.0, ramp_up_mw_per_hour=1000.0,
            ramp_down_mw_per_hour=1000.0,
            cost_linear_yuan_per_mwh=100.0,
            cost_quadratic_yuan_per_mw2h=0.0,
            emission_tco2_per_mwh=0.5,
        )],
        horizon_hours=2,
    )

    priced = engine._with_electricity_price_forecast(problem)

    assert priced.electricity_prices == pytest.approx([0.5005, 0.5045])


def test_marginal_price_forecast_uses_load_net_of_available_renewables():
    engine = object.__new__(SimulationEngine)
    engine.fixed_pricing = None
    engine.data_centers = []
    engine.pp_adapter = type(
        "Grid",
        (),
        {
            "electricity_strategy": MarginalElectricityPricing(
                base_price=0.5, sensitivity=0.02, scale=1000.0
            ),
            "get_bus_marginal_price": lambda self, bus: 0.5,
        },
    )()
    problem = PowerDispatchProblem(
        load_mw=[1000.0, 1000.0],
        renewables=[RenewableForecast("wind", 2, [800.0, 0.0])],
        horizon_hours=2,
    )

    priced = engine._with_electricity_price_forecast(problem)

    assert priced.electricity_prices == pytest.approx([0.501, 0.505])


def test_heuristic_cycle_optimizes_all_electrical_resources_and_power_balance():
    engine = object.__new__(SimulationEngine)
    engine.current_second = 0
    engine.optimization_config = {"mode": "none", "objective": "peak_shaving"}
    engine.pp_adapter = _PowerAdapter()

    cycle = engine._run_heuristic_cycle()
    result = engine.latest_power_dispatch_result

    assert cycle["status"] == "optimal"
    assert result.strictly_feasible is True
    assert set(result.generator_mw) == {"thermal"}
    assert set(result.renewable_dispatched_mw) == {"wind"}
    assert set(result.storage_soc_mwh) == {"battery"}
    assert cycle["storage_soc_mwh"]["battery"] == result.storage_soc_mwh["battery"][1]
    assert cycle["forecast_fill"] == "native"
    assert cycle["ac_validation_status"] == "validated"
    supplied = (
        result.generator_mw["thermal"][0]
        + result.renewable_dispatched_mw["wind"][0]
        + result.storage_power_mw["battery"][0]
    )
    assert supplied == pytest.approx(40.0)


def test_heuristic_cycle_uses_fine_grained_rolling_forecast():
    engine = object.__new__(SimulationEngine)
    engine.current_second = 0
    engine.optimization_config = {
        "mode": "none", "objective": "min_cost",
        "forecast_horizon_hours": 2.0, "forecast_step_minutes": 5.0,
    }
    engine.pp_adapter = _PowerAdapter()

    engine._run_heuristic_cycle()

    assert engine.pp_adapter.problem_kwargs["horizon_hours"] == pytest.approx(2.0)
    assert engine.pp_adapter.problem_kwargs["step_hours"] == pytest.approx(5.0 / 60.0)


def test_heuristic_cycle_restores_last_feasible_dispatch_after_ac_failure():
    engine = object.__new__(SimulationEngine)
    engine.current_second = 0
    engine.optimization_config = {"mode": "none", "objective": "min_cost"}
    engine.pp_adapter = _PowerAdapter(ac_feasible=False)

    cycle = engine._run_heuristic_cycle()

    assert cycle["status"] == "ac_validation_failed"
    assert engine.pp_adapter.restored is True


def test_heuristic_cycle_builds_and_validates_against_same_new_task_load():
    engine = object.__new__(SimulationEngine)
    engine.current_second = 0
    engine.optimization_config = {"mode": "none", "objective": "min_cost"}
    task = Task(
        user_id="u", task_type="general", required_compute=10,
        duration_hours=1,
    )
    center = DataCenter(
        id="dc", name="dc", grid_bus_id=3, total_compute=100,
        power_per_tflops=0.01,
    )
    expected_load = 2.0 + center.power_for_task_mw(task)

    class ProjectedAdapter(_PowerAdapter):
        def __init__(self):
            super().__init__()
            self.extra_loads = {3: 2.0}
            self.build_loads = []
            self.validation_loads = []

        def replace_compute_loads(self, loads):
            self.extra_loads = dict(loads)

        def build_power_dispatch_problem(self, *args, **kwargs):
            self.build_loads.append(dict(self.extra_loads))
            return super().build_power_dispatch_problem(*args, **kwargs)

        def validate_dispatch_ac(self):
            self.validation_loads.append(dict(self.extra_loads))
            return super().validate_dispatch_ac()

    engine.pp_adapter = ProjectedAdapter()
    engine.data_centers = [center]
    engine.dc_sims = {"dc": type("Sim", (), {"current_load_mw": 2.0})()}
    engine._heuristic_pending_projection = (
        {task.id: "dc"}, {task.id: task}
    )

    cycle = engine._run_heuristic_cycle()

    assert cycle["status"] == "optimal"
    assert engine.pp_adapter.build_loads == [{3: pytest.approx(expected_load)}]
    assert engine.pp_adapter.validation_loads == [{3: pytest.approx(expected_load)}]
    assert engine.pp_adapter.extra_loads == {3: 2.0}


def test_dispatch_mode_joint_uses_optimizer_assignment():
    engine = _dispatch_engine("joint")
    task = Task(user_id="u", task_type="general", compute_amount_tflop_hours=1, duration_hours=1)
    task.transition_to(TaskStatus.SCHEDULING)
    engine.ready_tasks = [task]
    called = []
    engine.optimize_ready_tasks = lambda tasks: (called.append(tasks) or {"status": "optimal", "assignments": {task.id: "dc-b"}})

    engine._dispatch_ready_tasks()

    assert len(called) == 1
    assert task.allocated_data_center_id == "dc-b"


def test_dispatch_batch_is_capped_before_joint_optimizer_runs():
    engine = _dispatch_engine("joint")
    engine.current_second = 0
    engine.scheduling_config = {
        "batch_interval_seconds": 1, "max_tasks_per_batch": 2,
    }
    tasks = [
        Task(
            user_id=f"u-{index}", task_type="general",
            required_compute=1, duration_hours=1,
        )
        for index in range(3)
    ]
    for task in tasks:
        task.transition_to(TaskStatus.SCHEDULING)
    engine.ready_tasks = list(tasks)
    optimized_batches = []

    def optimize(batch):
        optimized_batches.append(list(batch))
        return {
            "status": "optimal",
            "assignments": {task.id: "dc-a" for task in batch},
            "start_periods": {task.id: 0 for task in batch},
        }

    engine.optimize_ready_tasks = optimize

    engine._dispatch_ready_tasks()

    assert optimized_batches == [tasks[:2]]
    assert tasks[2] in engine.ready_tasks
    assert tasks[2].id not in engine.dispatched_task_ids


def test_future_joint_plan_does_not_consume_current_batch_slot():
    engine = _dispatch_engine("joint")
    engine.current_second = 0
    engine.scheduling_config = {
        "batch_interval_seconds": 1, "max_tasks_per_batch": 1,
    }
    future = Task(
        user_id="future", task_type="general", required_compute=1,
        duration_hours=1, max_wait_seconds=7200,
    )
    future._joint_not_before_second = 3600.0
    future._joint_planned_center = "dc-b"
    future.allocated_data_center_id = "dc-b"
    urgent = Task(
        user_id="urgent", task_type="general", required_compute=1,
        duration_hours=1, max_wait_seconds=10,
    )
    for task in (future, urgent):
        task.transition_to(TaskStatus.SCHEDULING)
    engine.ready_tasks = [future, urgent]
    optimized_batches = []

    def optimize(batch):
        optimized_batches.append(list(batch))
        return {
            "status": "optimal",
            "assignments": {urgent.id: "dc-a"},
            "start_periods": {urgent.id: 0},
        }

    engine.optimize_ready_tasks = optimize

    engine._dispatch_ready_tasks()

    assert optimized_batches == [[urgent]]
    assert urgent.id in engine.dispatched_task_ids
    assert future in engine.ready_tasks


def test_due_joint_plan_waits_when_revalidation_does_not_approve_assignment():
    engine = _dispatch_engine("joint")
    engine.current_second = 3600
    engine.scheduling_config = {
        "batch_interval_seconds": 1, "max_tasks_per_batch": 1,
    }
    task = Task(
        user_id="due", task_type="general", required_compute=1,
        duration_hours=1, max_wait_seconds=7200,
    )
    task.transition_to(TaskStatus.SCHEDULING)
    task._joint_not_before_second = 3600.0
    task._joint_planned_center = "dc-b"
    task.allocated_data_center_id = "dc-b"
    engine.ready_tasks = [task]
    engine.optimize_ready_tasks = lambda batch: {
        "status": "optimal", "assignments": {},
        "start_periods": {}, "queued_tasks": [task.id],
    }

    engine._dispatch_ready_tasks()

    assert task.id not in engine.dispatched_task_ids
    assert task in engine.ready_tasks
    assert task.allocated_data_center_id is None


def test_local_subset_retry_does_not_launch_rejected_fixed_center_task():
    engine = _dispatch_engine("hierarchical")
    engine.current_second = 0
    engine.scheduling_config = {
        "batch_interval_seconds": 1, "max_tasks_per_batch": 20,
    }
    accepted = Task(
        user_id="u-a", task_type="general", required_compute=1,
        duration_hours=1, user_specified_data_center="dc-a",
    )
    rejected = Task(
        user_id="u-b", task_type="general", required_compute=1,
        duration_hours=1, user_specified_data_center="dc-b",
    )
    for task in (accepted, rejected):
        task.transition_to(TaskStatus.SCHEDULING)
    engine.ready_tasks = [accepted, rejected]
    calls = []

    def optimize(batch):
        calls.append([task.id for task in batch])
        if len(calls) <= 2:
            return {"status": "infeasible", "assignments": {}}
        return {
            "status": "optimal",
            "assignments": {accepted.id: "dc-a"},
        }

    engine.optimize_ready_tasks = optimize

    engine._dispatch_ready_tasks()

    assert accepted.id in engine.dispatched_task_ids
    assert rejected.id not in engine.dispatched_task_ids
    assert rejected in engine.ready_tasks


def test_joint_ac_validation_failure_defers_whole_batch_without_subset_retries():
    engine = _dispatch_engine("joint")
    engine.current_second = 0
    engine.scheduling_config = {"batch_interval_seconds": 1, "max_tasks_per_batch": 20}
    tasks = [
        Task(user_id=f"u-{index}", task_type="general", required_compute=1, duration_hours=1)
        for index in range(3)
    ]
    for task in tasks:
        task.transition_to(TaskStatus.SCHEDULING)
    engine.ready_tasks = list(tasks)
    calls = []

    def optimize(batch):
        calls.append([task.id for task in batch])
        return {"status": "ac_validation_failed", "assignments": {}}

    engine.optimize_ready_tasks = optimize

    engine._dispatch_ready_tasks()

    assert calls == [[task.id for task in tasks]]
    assert engine.ready_tasks == tasks
    assert not engine.dispatched_task_ids


def test_joint_dispatch_honours_future_start_period_before_launching_task():
    engine = _dispatch_engine("joint")
    engine.current_second = 0
    engine.scheduling_config = {"batch_interval_seconds": 1}
    task = Task(
        user_id="u", task_type="general", required_compute=1,
        duration_hours=1, max_wait_seconds=7200,
    )
    task.transition_to(TaskStatus.SCHEDULING)
    engine.ready_tasks = [task]
    engine.optimize_ready_tasks = lambda tasks: {
        "status": "optimal", "assignments": {task.id: "dc-b"},
        "start_periods": {task.id: 0 if engine.current_second >= 300 else 1},
    }

    engine._dispatch_ready_tasks()

    assert task.id not in engine.dispatched_task_ids
    assert task in engine.ready_tasks
    assert task.allocated_data_center_id == "dc-b"

    engine.current_second = 300
    engine._dispatch_ready_tasks()

    assert task.id in engine.dispatched_task_ids


def test_joint_power_validation_includes_user_fixed_placement_tasks():
    engine = _dispatch_engine("joint")
    engine.current_second = 0
    task = Task(
        user_id="u", task_type="general", required_compute=1,
        duration_hours=1, user_specified_data_center="dc-a",
    )
    task.transition_to(TaskStatus.SCHEDULING)
    engine.ready_tasks = [task]
    seen = []
    engine.optimize_ready_tasks = lambda tasks: (
        seen.extend(tasks) or {
            "status": "optimal", "assignments": {task.id: "dc-a"},
            "start_periods": {task.id: 0},
        }
    )

    engine._dispatch_ready_tasks()

    assert seen == [task]
    assert task.id in engine.dispatched_task_ids


def test_joint_optimize_ready_tasks_routes_through_unified_coordinator(monkeypatch):
    engine = object.__new__(SimulationEngine)
    engine.current_second = 0
    engine.optimization_config = {"mode": "joint", "objective": "min_cost"}
    engine.scheduling_config = {}
    engine.data_centers = [DataCenter(id="dc", name="dc", total_compute=10)]
    engine.pp_adapter = _PowerAdapter()
    engine.storage_dispatch_result = {
        "status": "idle", "reason": "not_started",
        "requested_power_mw": 0.0, "actual_power_mw": 0.0,
        "price": None,
    }
    task_item = Task(user_id="u", task_type="general", required_compute=1, duration_hours=1)
    problem = engine.pp_adapter.build_power_dispatch_problem(0, horizon_hours=2)
    power = __import__("src.optimization.power_dispatch", fromlist=["PowerDispatchOptimizer"]).PowerDispatchOptimizer().solve(problem)

    captured = {}

    def solve(self, tasks, data_centers, power_problem, **kwargs):
        captured.update(kwargs)
        return JointCoordinationResult(
            status="optimal", objective_value=1.0,
            assignments={task_item.id: "dc"}, start_periods={task_item.id: 0},
            queued_tasks=[], generator_mw=power.generator_mw,
            renewable_dispatched_mw=power.renewable_dispatched_mw,
            renewable_curtailed_mw=power.renewable_curtailed_mw,
            storage_power_mw=power.storage_power_mw,
            storage_soc_mwh=power.storage_soc_mwh,
            objective_components=power.objective_components,
            strictly_feasible=True, forecast_fill=power.forecast_fill,
            power_dispatch=power,
        )

    monkeypatch.setattr("src.optimization.joint_coordination.JointCoordinationOptimizer.solve", solve)

    result = engine.optimize_ready_tasks([task_item])

    assert result["mode"] == "global"
    assert result["assignments"] == {task_item.id: "dc"}
    assert result["generator_mw"] == {"thermal": power.generator_mw["thermal"][0]}
    assert result["storage_soc_mwh"] == {"battery": power.storage_soc_mwh["battery"][1]}
    assert engine.storage_dispatch_result["reason"] != "not_started"
    assert engine.storage_dispatch_result["requested_power_mw"] == pytest.approx(
        power.storage_power_mw["battery"][0]
    )
    assert captured["minimum_active_center_tasks"] == 1


def test_joint_ac_validation_excludes_tasks_planned_for_future_periods(monkeypatch):
    engine = object.__new__(SimulationEngine)
    engine.current_second = 0
    engine.optimization_config = {"mode": "joint", "objective": "min_cost"}
    engine.scheduling_config = {}
    engine.data_centers = [DataCenter(id="dc", name="dc", grid_bus_id=1, total_compute=10)]
    engine.dc_sims = {"dc": type("Sim", (), {"current_load_mw": 0.0})()}
    engine.pp_adapter = _PowerAdapter()
    task_item = Task(user_id="u", task_type="general", required_compute=1, duration_hours=1)
    problem = engine.pp_adapter.build_power_dispatch_problem(0, horizon_hours=2)
    power = __import__("src.optimization.power_dispatch", fromlist=["PowerDispatchOptimizer"]).PowerDispatchOptimizer().solve(problem)
    observed = []

    def validate(power_dispatch, assignments, tasks_by_id):
        observed.append(dict(assignments))
        return {"feasible": True}

    engine._validate_candidate_ac = validate

    def solve(self, tasks, data_centers, power_problem, **kwargs):
        candidate = JointCoordinationResult(
            status="optimal", objective_value=1.0,
            assignments={task_item.id: "dc"}, start_periods={task_item.id: 1},
            queued_tasks=[], generator_mw=power.generator_mw,
            renewable_dispatched_mw=power.renewable_dispatched_mw,
            renewable_curtailed_mw=power.renewable_curtailed_mw,
            storage_power_mw=power.storage_power_mw,
            storage_soc_mwh=power.storage_soc_mwh,
            objective_components=power.objective_components,
            strictly_feasible=True, forecast_fill=power.forecast_fill,
            power_dispatch=power,
        )
        assert self.ac_validator(candidate, 1) is True
        return candidate

    monkeypatch.setattr("src.optimization.joint_coordination.JointCoordinationOptimizer.solve", solve)

    engine.optimize_ready_tasks([task_item])

    assert observed == [{}]


def test_dispatch_mode_hierarchical_schedules_then_optimizes():
    engine = _dispatch_engine("hierarchical")
    task = Task(user_id="u", task_type="general", compute_amount_tflop_hours=1, duration_hours=1)
    task.transition_to(TaskStatus.SCHEDULING)
    engine.ready_tasks = [task]
    called = []
    engine.optimize_ready_tasks = lambda tasks: (called.append(tasks) or {"status": "optimal", "assignments": {task.id: "dc-a"}})

    engine._dispatch_ready_tasks()

    assert len(called) == 1
    assert task.allocated_data_center_id == "dc-a"


def test_hierarchical_dispatch_applies_final_feedback_assignment():
    engine = _dispatch_engine("hierarchical")
    task = Task(user_id="u", task_type="general", required_compute=1, duration_hours=1)
    task.transition_to(TaskStatus.SCHEDULING)
    engine.ready_tasks = [task]
    engine.optimize_ready_tasks = lambda tasks: {
        "status": "optimal", "assignments": {task.id: "dc-b"}
    }

    engine._dispatch_ready_tasks()

    assert task.allocated_data_center_id == "dc-b"


def test_hierarchical_optimize_ready_tasks_routes_through_local_coordinator(monkeypatch):
    engine = object.__new__(SimulationEngine)
    engine.optimization_config = {"mode": "hierarchical", "objective": "min_cost"}
    engine.scheduling_config = {}
    engine.data_centers = [DataCenter(id="dc", name="dc", total_compute=10)]
    engine.pp_adapter = _PowerAdapter()
    task = Task(user_id="u", task_type="general", required_compute=1, duration_hours=1)
    dispatched_power = engine.pp_adapter.build_power_dispatch_problem(0, horizon_hours=2)
    power = __import__("src.optimization.power_dispatch", fromlist=["PowerDispatchOptimizer"]).PowerDispatchOptimizer().solve(dispatched_power)

    def solve(self, tasks, data_centers, task_context, power_problem_factory, **kwargs):
        return LocalCoordinationResult(
            status="optimal", assignments={task.id: "dc"}, power_dispatch=power,
            iterations=2, converged=True, objective_history=[2.0, 1.5],
        )

    monkeypatch.setattr("src.optimization.local_coordination.LocalCoordinationOptimizer.solve", solve)

    result = engine.optimize_ready_tasks([task])

    assert result["mode"] == "local"
    assert result["coordination_iterations"] == 2
    assert result["assignments"] == {task.id: "dc"}
    assert result["generator_mw"] == {"thermal": power.generator_mw["thermal"][0]}
    assert result["storage_soc_mwh"] == {"battery": power.storage_soc_mwh["battery"][1]}


def test_dispatch_reserves_compute_before_starting_batch_tasks():
    engine = object.__new__(SimulationEngine)
    engine.env = simpy.Environment()
    engine.ready_tasks = []
    engine.dispatched_task_ids = set()
    engine.optimization_config = {"mode": "none"}
    engine.scheduling_config = {"batch_interval_seconds": 1, "max_tasks_per_batch": 20}
    center = DataCenter(id="dc", name="dc", total_compute=10)
    engine.data_centers = [center]
    engine.dc_sims = {"dc": _FakeSim()}
    engine.scheduler = type("Scheduler", (), {"select_data_center": lambda self, task, dcs: dcs[0]})()
    engine.current_second = 0
    first = Task(user_id="u", task_type="general", compute_amount_tflop_hours=8, duration_hours=1)
    second = Task(user_id="u", task_type="general", compute_amount_tflop_hours=8, duration_hours=1)
    first.transition_to(TaskStatus.SCHEDULING)
    second.transition_to(TaskStatus.SCHEDULING)
    engine.ready_tasks = [first, second]

    engine._dispatch_ready_tasks()

    assert first.allocated_data_center_id == "dc"
    assert second.allocated_data_center_id is None
    assert center.used_compute == 8
    assert engine.ready_tasks == [second]


def test_dispatch_skips_blocked_gpu_task_and_runs_later_feasible_task():
    engine = object.__new__(SimulationEngine)
    engine.env = simpy.Environment()
    engine.dispatched_task_ids = set()
    engine.optimization_config = {"mode": "none"}
    engine.scheduling_config = {"batch_interval_seconds": 5, "max_tasks_per_batch": 1}
    center = DataCenter(
        id="dc", name="dc", total_compute=100,
        device_pool=[DeviceSpec(
            model="GPU-H100", equipment_type="compute", quantity=1,
            compute_tflops=80, rated_power_kw=0.7,
        )],
    )
    occupying = Task(user_id="u", task_type="ai_training", required_compute=10, duration_hours=1, required_gpu_count=1)
    center.allocate(occupying)
    engine.data_centers = [center]
    engine.dc_sims = {"dc": _FakeSim()}
    engine.scheduler = type("Scheduler", (), {"select_data_center": lambda self, task, dcs: next(dc for dc in dcs if dc.can_allocate(task))})()
    engine.current_second = 5

    blocked = Task(user_id="u", task_type="ai_training", required_compute=10, duration_hours=1, required_gpu_count=1)
    feasible = Task(user_id="u", task_type="general", required_compute=10, duration_hours=1, required_gpu_count=0)
    blocked.transition_to(TaskStatus.SCHEDULING)
    feasible.transition_to(TaskStatus.SCHEDULING)
    engine.ready_tasks = [blocked, feasible]

    engine._dispatch_ready_tasks()

    assert feasible.allocated_data_center_id == "dc"
    assert blocked.allocated_data_center_id is None
    assert engine.ready_tasks == [blocked]


def test_dispatch_runs_when_step_crosses_batch_boundary():
    engine = object.__new__(SimulationEngine)
    engine.env = simpy.Environment()
    engine.dispatched_task_ids = set()
    engine.optimization_config = {"mode": "none"}
    engine.scheduling_config = {"batch_interval_seconds": 5, "max_tasks_per_batch": 20}
    center = DataCenter(id="dc", name="dc", total_compute=10)
    engine.data_centers = [center]
    engine.dc_sims = {"dc": _FakeSim()}
    engine.ready_tasks = []
    engine.current_second = 6
    engine._last_dispatch_second = 0
    task = Task(user_id="u", task_type="general", required_compute=1, duration_hours=1)
    task.transition_to(TaskStatus.SCHEDULING)
    engine.ready_tasks = [task]
    engine.optimize_ready_tasks = lambda tasks: {"status": "optimal", "assignments": {}}
    engine.scheduler = type("Scheduler", (), {"select_data_center": lambda self, task, dcs: dcs[0]})()

    engine._dispatch_ready_tasks()

    assert engine._last_dispatch_second == 6


def test_coordinated_dispatch_batches_tasks_without_dropping_them():
    """A costly coordinated solve waits for its batch window, but queued work survives."""
    engine = _dispatch_engine("hierarchical")
    engine.scheduling_config = {"batch_interval_seconds": 5, "max_tasks_per_batch": 20}
    engine.optimization_config = {
        "mode": "hierarchical", "task_batch_interval_seconds": 60,
    }
    engine.current_second = 5
    engine._last_dispatch_second = 0
    task = Task(user_id="u", task_type="general", required_compute=1, duration_hours=1)
    task.transition_to(TaskStatus.SCHEDULING)
    engine.ready_tasks = [task]
    optimized_batches = []
    engine.optimize_ready_tasks = lambda tasks: (
        optimized_batches.append(list(tasks))
        or {"status": "optimal", "assignments": {task.id: "dc-a"}}
    )

    engine._dispatch_ready_tasks()

    assert engine.ready_tasks == [task]
    assert optimized_batches == []

    engine.current_second = 60
    engine._dispatch_ready_tasks()

    assert optimized_batches == [[task]]
    assert task.allocated_data_center_id == "dc-a"


def test_coordinated_dispatch_does_not_batch_past_task_deadline():
    """A short-wait task must trigger coordination before its batching window ends."""
    engine = _dispatch_engine("hierarchical")
    engine.scheduling_config = {"batch_interval_seconds": 5, "max_tasks_per_batch": 20}
    engine.optimization_config = {
        "mode": "hierarchical", "task_batch_interval_seconds": 300,
    }
    engine.current_second = 5
    engine._last_dispatch_second = 0
    task = Task(
        user_id="u", task_type="general", required_compute=1, duration_hours=1,
        max_wait_seconds=30,
    )
    task.transition_to(TaskStatus.SCHEDULING)
    engine.ready_tasks = [task]
    optimized_batches = []
    engine.optimize_ready_tasks = lambda tasks: (
        optimized_batches.append(list(tasks))
        or {"status": "optimal", "assignments": {task.id: "dc-a"}}
    )

    engine._dispatch_ready_tasks()

    assert optimized_batches == [[task]]
    assert task.allocated_data_center_id == "dc-a"


def test_coordinated_dispatch_waits_when_next_batch_precedes_task_deadline():
    """Tasks wait for the real next coordinated batch instead of triggering a solve per arrival."""
    engine = _dispatch_engine("hierarchical")
    engine.scheduling_config = {"batch_interval_seconds": 5, "max_tasks_per_batch": 20}
    engine.optimization_config = {
        "mode": "hierarchical", "task_batch_interval_seconds": 300,
    }
    engine.current_second = 60
    engine._last_dispatch_second = 0
    task = Task(
        user_id="u", task_type="general", required_compute=1,
        duration_hours=1, submitted_at=60, max_wait_seconds=270,
    )
    task.transition_to(TaskStatus.SCHEDULING)
    engine.ready_tasks = [task]
    optimized_batches = []
    engine.optimize_ready_tasks = lambda tasks: (
        optimized_batches.append(list(tasks))
        or {"status": "optimal", "assignments": {task.id: "dc-a"}}
    )

    engine._dispatch_ready_tasks()

    assert engine.ready_tasks == [task]
    assert optimized_batches == []

    engine.current_second = 300
    engine._dispatch_ready_tasks()

    assert optimized_batches == [[task]]


def test_release_pending_tasks_only_scans_arrived_sorted_prefix():
    engine = object.__new__(SimulationEngine)
    engine.current_second = 5
    arrived = Task(user_id="u", task_type="general", required_compute=1, duration_hours=1, submitted_at=0)
    future = Task(user_id="u", task_type="general", required_compute=1, duration_hours=1, submitted_at=10)
    engine.pending_tasks = [arrived, future]
    engine.ready_tasks = []

    engine._release_pending_tasks()

    assert engine.ready_tasks == [arrived]
    assert engine.pending_tasks == [future]
