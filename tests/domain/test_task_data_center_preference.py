from src.domain.task import Task


def test_task_keeps_optional_user_selected_data_center():
    task = Task(
        user_id="u", task_type="general", compute_amount_tflop_hours=1,
        duration_hours=1, user_specified_data_center="DC2",
    )
    assert task.user_specified_data_center == "DC2"


def test_empty_user_selected_data_center_remains_unassigned():
    task = Task(
        user_id="u", task_type="general", compute_amount_tflop_hours=1,
        duration_hours=1,
    )
    assert task.user_specified_data_center is None
