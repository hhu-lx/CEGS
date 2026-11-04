from src.data.synthetic_tasks import SyntheticTaskDataFactory
from src.domain.task import Task


def test_factory_fills_only_missing_values_deterministically():
    task = Task(
        user_id="u1",
        task_type="rendering",
        compute_amount_tflop_hours=4,
        duration_hours=1,
        data_size_gb=None,
        required_cpu_cores=None,
        required_gpu_count=3,
    )

    completed = SyntheticTaskDataFactory(seed=7).complete(task)
    again = SyntheticTaskDataFactory(seed=7).complete(task.model_copy(deep=True))

    assert completed.data_size_gb == again.data_size_gb
    assert completed.required_cpu_cores == again.required_cpu_cores
    assert completed.required_gpu_count == 3
