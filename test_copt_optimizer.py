from src.domain.datacenter import DataCenter
from src.domain.task import Task
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
