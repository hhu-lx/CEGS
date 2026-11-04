import random

from src.domain.task import Task


class SyntheticTaskDataFactory:
    """Fills only missing optional task inputs with seed-stable values."""

    _DATA_SIZE_RANGES = {
        "ai_training": (50.0, 200.0),
        "rendering": (20.0, 120.0),
        "scientific": (10.0, 80.0),
        "web_service": (0.1, 5.0),
        "general": (1.0, 20.0),
    }

    def __init__(self, seed: int = 42):
        self.seed = seed

    def complete(self, task: Task) -> Task:
        # Derive a per-task stream so completion remains repeatable and stateless.
        randomizer = random.Random(f"{self.seed}:{task.id}:{task.task_type}")
        lower, upper = self._DATA_SIZE_RANGES.get(task.task_type, (1.0, 20.0))
        if task.data_size_gb is None:
            task.data_size_gb = round(randomizer.uniform(lower, upper), 2)
        if task.required_cpu_cores is None:
            task.required_cpu_cores = randomizer.choice((2, 4, 8, 16))
        if task.required_gpu_count is None:
            task.required_gpu_count = 1 if task.task_type in {"ai_training", "rendering"} else 0
        if task.required_gpu_count and task.required_gpu_type is None:
            task.required_gpu_type = randomizer.choice(("V100", "T4"))
        task.compute_bandwidth_requirement()
        return task
