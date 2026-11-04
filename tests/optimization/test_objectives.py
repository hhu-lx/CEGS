from src.domain.datacenter import DataCenter
from src.domain.task import Task
from src.optimization.copt_optimizer import CoptOptimizer


def test_copt_carbon_objective_prefers_lower_carbon_center_over_lower_price():
    task = Task(user_id="u", task_type="general", compute_amount_tflop_hours=1, duration_hours=1)
    cheap_dirty = DataCenter(id="dirty", name="dirty", total_compute=10, current_price=1, grid_bus_id=3)
    clean_costly = DataCenter(id="clean", name="clean", total_compute=10, current_price=2, grid_bus_id=4)

    result = CoptOptimizer().assign_tasks(
        [task], [cheap_dirty, clean_costly], objective="min_carbon", carbon_intensity={3: 0.8, 4: 0.1}
    )

    assert result.assignments == {task.id: "clean"}
