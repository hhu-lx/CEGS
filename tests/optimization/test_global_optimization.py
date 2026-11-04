from src.domain.datacenter import DataCenter
from src.domain.task import Task
from src.optimization.copt_optimizer import CoptOptimizer


def test_global_mode_returns_assignment_and_economic_carbon_breakdown():
    task = Task(user_id="u", task_type="general", compute_amount_tflop_hours=1, duration_hours=1)
    center = DataCenter(id="dc", name="dc", total_compute=10, current_price=2, grid_bus_id=3)

    result = CoptOptimizer().global_optimize([task], [center], carbon_intensity={3: 0.4})

    assert result.status == "optimal"
    assert result.assignments == {task.id: "dc"}
    assert result.economic_cost > 0
    assert result.carbon_emission > 0
