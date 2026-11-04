from src.domain.task import Task
from src.domain.enums import TaskStatus
from src.simulation.engine import SimulationEngine


class _Env:
    def __init__(self):
        self.processed = []

    def process(self, event):
        self.processed.append(event)


class _Sim:
    def run_task(self, task):
        return task


def test_dispatch_uses_user_selected_data_center_before_scheduler():
    task = Task(
        user_id="u", task_type="general", compute_amount_tflop_hours=1,
        duration_hours=1, user_specified_data_center="preferred",
    )
    task.transition_to(TaskStatus.SCHEDULING)
    engine = object.__new__(SimulationEngine)
    engine.ready_tasks = [task]
    engine.dispatched_task_ids = set()
    engine.dc_sims = {"preferred": _Sim()}
    engine.env = _Env()
    engine.data_centers = []
    engine.scheduler = None

    engine._dispatch_ready_tasks()

    assert task.allocated_data_center_id == "preferred"
    assert engine.env.processed == [task]
