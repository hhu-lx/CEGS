from src.simulation.engine import SimulationEngine, format_emission_log, format_idle_log
from src.domain.task import Task
from src.domain.enums import TaskStatus


class FakeGrid:
    def __init__(self):
        self.events = []

    def update_time_series(self, second):
        self.events.append(("time_series", second))

    def run_power_flow(self):
        self.events.append(("power_flow",))

    def get_bus_marginal_price(self, bus_id):
        return 0.42


class FakeCenter:
    grid_bus_id = 3

    def __init__(self):
        self.price = None

    def update_price(self, price):
        self.price = price


def test_emission_console_log_is_safe_for_windows_gbk():
    assert format_emission_log(12.345) == "  全网排放率: 12.35 吨CO2/h"
    format_emission_log(12.345).encode("gbk")


def test_idle_console_log_is_safe_for_windows_gbk():
    assert format_idle_log() == "  当前无运行任务"
    format_idle_log().encode("gbk")


def test_step_updates_grid_prices_and_records_at_configured_interval():
    engine = object.__new__(SimulationEngine)
    engine.current_second = 0
    engine.step_seconds = 1
    engine.pp_adapter = FakeGrid()
    engine.data_centers = [FakeCenter()]
    engine.stats_interval_seconds = 1
    engine.stats_count = 0
    engine._dispatch_storage = lambda: engine.pp_adapter.events.append(("storage_dispatch",))
    engine._release_pending_tasks = lambda: engine.pp_adapter.events.append(("release",))
    engine._dispatch_ready_tasks = lambda: engine.pp_adapter.events.append(("dispatch",))
    engine._dispatch_renewables = lambda: engine.pp_adapter.events.append(("renewable_dispatch",))
    engine._record_stats = lambda: engine.pp_adapter.events.append(("record",))

    SimulationEngine.step(engine)

    assert engine.current_second == 1
    assert engine.data_centers[0].price == 0.42
    assert engine.pp_adapter.events == [("storage_dispatch",), ("time_series", 1), ("power_flow",), ("release",), ("dispatch",), ("renewable_dispatch",), ("record",)]


def test_step_optimizes_renewables_every_five_seconds_and_reuses_dispatch_between_runs():
    engine = object.__new__(SimulationEngine)
    engine.current_second = 0
    engine.step_seconds = 1
    engine.pp_adapter = FakeGrid()
    engine.data_centers = [FakeCenter()]
    engine.stats_interval_seconds = 1
    engine.renewable_optimization_interval_seconds = 5
    engine.stats_count = 0
    engine._last_renewable_optimization_second = None
    engine._dispatch_storage = lambda: None
    engine._release_pending_tasks = lambda: None
    engine._dispatch_ready_tasks = lambda: None
    engine._dispatch_renewables = lambda: engine.pp_adapter.events.append(("renewable_optimize", engine.current_second))
    engine._reuse_renewable_dispatch = lambda: engine.pp_adapter.events.append(("renewable_reuse", engine.current_second))
    engine._record_stats = lambda: None

    for _ in range(6):
        SimulationEngine.step(engine)

    renewable_events = [event for event in engine.pp_adapter.events if event[0].startswith("renewable_")]
    assert renewable_events == [
        ("renewable_optimize", 1),
        ("renewable_reuse", 2),
        ("renewable_reuse", 3),
        ("renewable_reuse", 4),
        ("renewable_reuse", 5),
        ("renewable_optimize", 6),
    ]


def test_step_does_not_refresh_power_flow_until_configured_interval():
    engine = object.__new__(SimulationEngine)
    engine.current_second = 0
    engine.step_seconds = 1
    engine.power_flow_interval_seconds = 300
    engine.pp_adapter = FakeGrid()
    engine.data_centers = [FakeCenter()]
    engine.stats_interval_seconds = 9999
    engine.stats_count = 0
    engine.optimization_config = {"mode": "none"}
    engine._last_power_flow_second = None
    engine._last_renewable_optimization_second = None
    engine.renewable_optimization_interval_seconds = 300
    engine._release_pending_tasks = lambda: None
    engine._dispatch_ready_tasks = lambda: None
    engine._run_heuristic_cycle = lambda: None
    engine._reuse_renewable_dispatch = lambda: None
    for _ in range(299):
        SimulationEngine.step(engine)
    assert [event for event in engine.pp_adapter.events if event[0] == "power_flow"] == [("power_flow",)]
    for _ in range(2):
        SimulationEngine.step(engine)
    assert [event for event in engine.pp_adapter.events if event[0] == "power_flow"] == [
        ("power_flow",), ("power_flow",)
    ]


def test_step_routes_explicit_modes_to_their_complete_power_cycles():
    expected = {
        "none": "heuristic_cycle",
        "hierarchical": "local_cycle",
        "joint": "joint_cycle",
    }
    for mode, event in expected.items():
        engine = object.__new__(SimulationEngine)
        engine.current_second = 0
        engine.step_seconds = 1
        engine.optimization_config = {"mode": mode}
        engine.pp_adapter = FakeGrid()
        engine.data_centers = [FakeCenter()]
        engine.stats_interval_seconds = 10
        engine.stats_count = 0
        engine._last_renewable_optimization_second = None
        engine.renewable_optimization_interval_seconds = 5
        engine._dispatch_storage = lambda: engine.pp_adapter.events.append(("legacy_storage",))
        engine._release_pending_tasks = lambda: None
        engine._dispatch_ready_tasks = lambda: None
        engine._run_heuristic_cycle = lambda: engine.pp_adapter.events.append(("heuristic_cycle",))
        engine._run_local_coordination = lambda tasks: engine.pp_adapter.events.append(("local_cycle",))
        engine._run_joint_coordination = lambda tasks: engine.pp_adapter.events.append(("joint_cycle",))
        engine._reuse_renewable_dispatch = lambda: None
        engine._record_stats = lambda: None

        SimulationEngine.step(engine)

        assert (event,) in engine.pp_adapter.events
        assert ("legacy_storage",) not in engine.pp_adapter.events


def test_periodic_cpf_and_report_work_use_independent_intervals():
    engine = object.__new__(SimulationEngine)
    engine.current_second = 1
    engine.cpf_interval_seconds = 30
    engine.report_interval_seconds = 5
    engine._last_cpf_second = None
    engine._last_report_second = None

    assert SimulationEngine._periodic_due(engine, "_last_cpf_second", engine.cpf_interval_seconds)
    assert SimulationEngine._periodic_due(engine, "_last_report_second", engine.report_interval_seconds)

    engine.current_second = 5
    assert not SimulationEngine._periodic_due(engine, "_last_cpf_second", engine.cpf_interval_seconds)
    assert not SimulationEngine._periodic_due(engine, "_last_report_second", engine.report_interval_seconds)

    engine.current_second = 6
    assert SimulationEngine._periodic_due(engine, "_last_report_second", engine.report_interval_seconds)

    engine.current_second = 31
    assert SimulationEngine._periodic_due(engine, "_last_cpf_second", engine.cpf_interval_seconds)


def test_record_stats_exposes_running_compute_by_data_center():
    engine = object.__new__(SimulationEngine)
    task_a = Task(id="a", user_id="u", task_type="batch", required_compute=25, duration_hours=1)
    task_b = Task(id="b", user_id="u", task_type="batch", required_compute=15, duration_hours=1)
    task_a.status = TaskStatus.RUNNING
    task_b.status = TaskStatus.RUNNING
    engine.dc_sims = {
        "DC1": type("Sim", (), {"dc": type("DC", (), {"name": "北京中心"})(), "running_tasks": [task_a]})(),
        "DC2": type("Sim", (), {"dc": type("DC", (), {"name": "上海中心"})(), "running_tasks": [task_b]})(),
    }

    assert SimulationEngine._running_compute_by_datacenter(engine) == {
        "DC1": {"name": "北京中心", "compute_tflops": 25.0},
        "DC2": {"name": "上海中心", "compute_tflops": 15.0},
    }


def test_record_stats_exposes_datacenter_runtime_summary():
    engine = object.__new__(SimulationEngine)
    engine.dc_sims = {
        "DC1": type("Sim", (), {
            "dc": type("DC", (), {"name": "北京中心", "total_compute": 100.0, "used_compute": 25.0, "total_bandwidth": 1000.0, "used_bandwidth": 200.0})(),
            "running_tasks": [], "current_load_mw": 3.5,
        })(),
    }
    assert SimulationEngine._datacenter_runtime_summary(engine) == {
        "DC1": {
            "name": "北京中心", "total_compute": 100.0, "used_compute": 25.0,
            "compute_utilization": 0.25, "total_bandwidth": 1000.0,
            "used_bandwidth": 200.0, "bandwidth_utilization": 0.2,
            "running_tasks": 0, "power_mw": 3.5,
        }
    }
