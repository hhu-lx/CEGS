import pytest

from src.domain.enums import TaskStatus
from src.domain.task import Task


def test_ready_task_cancels_after_its_wait_deadline():
    task = Task(
        user_id="u1",
        task_type="ai_training",
        compute_amount_tflop_hours=12,
        duration_hours=2,
        submitted_at=10,
        max_wait_hours=0.5,
    )

    assert task.is_expired(1811) is True
    task.cancel("wait_timeout")

    assert task.status == TaskStatus.CANCELLED
    assert task.cancel_reason == "wait_timeout"


def test_task_disallows_invalid_status_transition():
    task = Task(user_id="u1", task_type="general", compute_amount_tflop_hours=1, duration_hours=1)

    with pytest.raises(ValueError, match="invalid task transition"):
        task.transition_to(TaskStatus.COMPLETED)


def test_task_transitions_through_scheduling_before_running():
    task = Task(user_id="u1", task_type="general", compute_amount_tflop_hours=1, duration_hours=1)

    task.transition_to(TaskStatus.SCHEDULING)
    task.transition_to(TaskStatus.RUNNING)

    assert task.status == TaskStatus.RUNNING


def test_task_has_explicit_submitted_state():
    task = Task(user_id="u1", task_type="general", compute_amount_tflop_hours=1, duration_hours=1)

    assert task.status == TaskStatus.SUBMITTED
