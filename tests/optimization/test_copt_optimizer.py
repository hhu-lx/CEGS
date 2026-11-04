from src.domain.datacenter import DataCenter
from src.domain.task import Task
from src.domain.storage import EnergyStorage
from src.optimization.copt_optimizer import CoptOptimizer


def test_copt_assigns_task_to_the_only_feasible_center():
    task = Task(user_id="u1", task_type="general", compute_amount_tflop_hours=4, duration_hours=1)
    infeasible = DataCenter(id="small", name="small", total_compute=2, current_price=1)
    feasible = DataCenter(id="large", name="large", total_compute=8, current_price=2)

    result = CoptOptimizer().assign_tasks([task], [infeasible, feasible])

    assert result.status == "optimal"
    assert result.assignments == {task.id: feasible.id}


def test_copt_honours_user_specified_data_center():
    task = Task(
        user_id="u1", task_type="general", compute_amount_tflop_hours=1,
        duration_hours=1, user_specified_data_center="preferred",
    )
    cheap = DataCenter(id="cheap", name="cheap", total_compute=8, current_price=0.1)
    preferred = DataCenter(id="preferred", name="preferred", total_compute=8, current_price=10)

    result = CoptOptimizer().assign_tasks([task], [cheap, preferred])

    assert result.status == "optimal"
    assert result.assignments == {task.id: "preferred"}


def test_local_feedback_can_reassign_a_provisional_automatic_placement():
    task = Task(
        user_id="u1", task_type="general", required_compute=1,
        duration_hours=1, allocated_data_center_id="expensive",
    )
    expensive = DataCenter(id="expensive", name="expensive", total_compute=8, current_price=9)
    cheap = DataCenter(id="cheap", name="cheap", total_compute=8, current_price=1)

    result = CoptOptimizer().assign_tasks(
        [task], [expensive, cheap], respect_allocated_data_center=False
    )

    assert result.assignments == {task.id: "cheap"}


def test_assign_tasks_accepts_custom_objective_function():
    task = Task(user_id="u", task_type="general", compute_amount_tflop_hours=1, duration_hours=1)
    centers = [
        DataCenter(id="dc1", name="one", total_compute=10, current_price=0.1),
        DataCenter(id="dc2", name="two", total_compute=10, current_price=0.1),
    ]
    result = CoptOptimizer().assign_tasks(
        [task], centers,
        objective_function=lambda t, dc, context: 0.0 if dc.id == "dc2" else 10.0,
    )

    assert result.status == "optimal"
    assert result.assignments == {task.id: "dc2"}


def test_copt_uses_data_center_with_sufficient_network_capacity():
    task = Task(
        user_id="u", task_type="general", required_compute=10, duration_hours=0.04,
        data_size_gb=100,
    )
    constrained = DataCenter(id="slow-net", name="slow", total_compute=100, total_bandwidth=4_000)
    capable = DataCenter(id="fast-net", name="fast", total_compute=100, total_bandwidth=100_000)

    result = CoptOptimizer().assign_tasks([task], [constrained, capable])

    assert result.status == "optimal"
    assert result.assignments == {task.id: "fast-net"}


def test_copt_rejects_batch_whose_aggregate_bandwidth_exceeds_center_capacity():
    tasks = [
        Task(
            user_id=f"u-{index}", task_type="general", required_compute=10,
            duration_hours=1, required_bandwidth_mbps=60,
        )
        for index in range(2)
    ]
    center = DataCenter(
        id="dc", name="dc", total_compute=100, total_bandwidth=100
    )

    result = CoptOptimizer().assign_tasks(tasks, [center])

    assert result.status == "infeasible"
    assert result.assignments == {}


def test_copt_soft_load_balance_splits_equal_cost_batch():
    centers = [
        DataCenter(id="a", name="a", total_compute=100, current_price=1),
        DataCenter(id="b", name="b", total_compute=100, current_price=1),
    ]
    tasks = [
        Task(id=f"t-{index}", user_id="u", task_type="general", required_compute=20, duration_hours=1)
        for index in range(4)
    ]

    result = CoptOptimizer().assign_tasks(tasks, centers, load_balance_weight=1.0)

    assert result.status == "optimal"
    assert sum(center_id == "a" for center_id in result.assignments.values()) == 2
    assert sum(center_id == "b" for center_id in result.assignments.values()) == 2


def test_copt_activity_floor_uses_every_eligible_center_despite_cost_preference():
    centers = [
        DataCenter(id="a", name="a", total_compute=100, current_price=1),
        DataCenter(id="b", name="b", total_compute=100, current_price=10),
        DataCenter(id="c", name="c", total_compute=100, current_price=20),
    ]
    tasks = [
        Task(id=f"t-{index}", user_id="u", task_type="general", required_compute=10, duration_hours=1)
        for index in range(5)
    ]

    result = CoptOptimizer().assign_tasks(
        tasks, centers, minimum_active_center_tasks=1,
    )

    assert result.status == "optimal"
    assert set(result.assignments.values()) == {"a", "b", "c"}


def test_copt_activity_floor_is_not_applied_when_batch_is_smaller_than_eligible_centers():
    centers = [
        DataCenter(id="a", name="a", total_compute=100, current_price=1),
        DataCenter(id="b", name="b", total_compute=100, current_price=10),
        DataCenter(id="c", name="c", total_compute=100, current_price=20),
    ]
    tasks = [
        Task(id=f"t-{index}", user_id="u", task_type="general", required_compute=10, duration_hours=1)
        for index in range(2)
    ]

    result = CoptOptimizer().assign_tasks(
        tasks, centers, minimum_active_center_tasks=1,
    )

    assert result.status == "optimal"
    assert set(result.assignments.values()) == {"a"}


def test_realtime_storage_objective_discharges_above_reference_load():
    storage = EnergyStorage(
        id="s", bus_id=3, capacity_mwh=10, max_power_mw=4,
        initial_soc_mwh=5, min_soc_mwh=1,
    )

    result = CoptOptimizer().optimize_storage_realtime(
        storage,
        net_load_mw=110,
        reference_load_mw=100,
        electricity_price=0.5,
        step_hours=1,
        weights={"cost": 0, "peak_shaving": 1, "storage_degradation": 0},
    )

    assert result["status"] == "optimal"
    assert result["power_mw"] > 0
    assert result["net_load_after_storage_mw"] < 110


def test_realtime_storage_objective_charges_below_reference_load():
    storage = EnergyStorage(
        id="s", bus_id=3, capacity_mwh=10, max_power_mw=4,
        initial_soc_mwh=5, min_soc_mwh=1,
    )

    result = CoptOptimizer().optimize_storage_realtime(
        storage,
        net_load_mw=90,
        reference_load_mw=100,
        electricity_price=0.5,
        step_hours=1,
        weights={"cost": 0, "peak_shaving": 1, "storage_degradation": 0},
    )

    assert result["status"] == "optimal"
    assert result["power_mw"] < 0
    assert result["net_load_after_storage_mw"] > 90
