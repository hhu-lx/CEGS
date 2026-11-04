from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator

from .enums import TaskStatus


class Task(BaseModel):
    """A user-submitted computation request and its controlled lifecycle."""

    model_config = ConfigDict(extra="allow")
    _simulation_started: bool = PrivateAttr(default=False)

    id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: str
    task_type: str
    duration_hours: float = Field(gt=0)
    compute_amount_tflop_hours: Optional[float] = Field(default=None, gt=0)
    required_compute: float = Field(default=0.0, ge=0)
    region: str = "region_a"
    max_budget: Optional[float] = None
    priority: int = 1
    status: TaskStatus = TaskStatus.SUBMITTED
    submitted_at: float = Field(default=0.0, ge=0)
    # Canonical waiting limit in simulation seconds.  Keep max_wait_hours as
    # a compatibility input for older API clients and task files.
    max_wait_seconds: Optional[float] = Field(default=None, ge=0)
    max_wait_hours: float = Field(default=1.0, ge=0)
    allocated_data_center_id: Optional[str] = None
    # Optional user preference from the task data table.  When populated,
    # dispatch and COPT must honour this placement rather than reassigning it.
    user_specified_data_center: Optional[str] = None
    cancel_reason: Optional[str] = None
    data_size_gb: Optional[float] = Field(default=None, ge=0)
    required_bandwidth_mbps: float = Field(default=0.0, ge=0)
    required_cpu_cores: Optional[int] = Field(default=None, ge=0)
    required_gpu_count: Optional[int] = Field(default=None, ge=0)
    required_gpu_type: Optional[str] = None
    gpu_type: Optional[str] = None
    plan_gpu: Optional[float] = None
    actual_start_second: Optional[float] = None
    actual_end_second: Optional[float] = None
    actual_execution_seconds: Optional[float] = None
    actual_power_mw: Optional[float] = None

    @model_validator(mode="after")
    def derive_compute_fields(self) -> "Task":
        if self.required_compute == 0 and self.compute_amount_tflop_hours is not None:
            self.required_compute = self.compute_amount_tflop_hours / self.duration_hours
        if self.compute_amount_tflop_hours is None:
            self.compute_amount_tflop_hours = self.required_compute * self.duration_hours
        return self

    @property
    def deadline_second(self) -> float:
        wait_seconds = self.max_wait_seconds if self.max_wait_seconds is not None else self.max_wait_hours * 3600
        return self.submitted_at + wait_seconds

    def is_expired(self, now_second: float) -> bool:
        return self.status in {TaskStatus.SUBMITTED, TaskStatus.PENDING, TaskStatus.READY, TaskStatus.SCHEDULING} and now_second > self.deadline_second

    def transition_to(self, status: TaskStatus) -> None:
        allowed = {
            TaskStatus.SUBMITTED: {TaskStatus.SCHEDULING, TaskStatus.RUNNING, TaskStatus.PENDING, TaskStatus.CANCELLED, TaskStatus.REJECTED},
            TaskStatus.PENDING: {TaskStatus.READY, TaskStatus.SCHEDULING, TaskStatus.CANCELLED, TaskStatus.REJECTED},
            TaskStatus.READY: {TaskStatus.SCHEDULING, TaskStatus.RUNNING, TaskStatus.CANCELLED, TaskStatus.REJECTED},
            TaskStatus.SCHEDULING: {TaskStatus.RUNNING, TaskStatus.CANCELLED, TaskStatus.REJECTED},
            TaskStatus.RUNNING: {TaskStatus.COMPLETED},
            TaskStatus.COMPLETED: set(),
            TaskStatus.CANCELLED: set(),
            TaskStatus.REJECTED: set(),
        }
        if status not in allowed[self.status]:
            raise ValueError(f"invalid task transition: {self.status} -> {status}")
        self.status = status

    def cancel(self, reason: str) -> None:
        self.transition_to(TaskStatus.CANCELLED)
        self.cancel_reason = reason

    def compute_bandwidth_requirement(self) -> float:
        if not self.data_size_gb:
            return 0.0
        self.required_bandwidth_mbps = (self.data_size_gb * 8192) / (self.duration_hours * 3600)
        return self.required_bandwidth_mbps
