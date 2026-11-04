import math
from typing import Union
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from src.domain.device import DeviceSpec
from src.domain.task import Task
from src.strategies.pricing.base import PricingStrategy


class DataCenter(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    region: str = "region_a"
    grid_bus_id: int = 3
    total_compute: float = Field(gt=0)
    used_compute: float = Field(default=0.0, ge=0)
    total_bandwidth: float = Field(default=1000.0, gt=0)
    used_bandwidth: float = Field(default=0.0, ge=0)
    pue: float = Field(default=1.0, ge=1.0)
    device_pool: list[DeviceSpec] = Field(default_factory=list)
    power_per_tflops: float = Field(default=0.5, gt=0)
    power_scale: float = Field(default=1.0, gt=0)
    profit_margin: float = Field(default=1.3, gt=0)
    current_price: float = Field(default=1.0, ge=0)
    _pricing_strategy: PricingStrategy = PrivateAttr()
    _used_devices: dict[str, int] = PrivateAttr(default_factory=dict)
    _GENERIC_GPU_KEY = "__generic_compute_gpu__"
    _VIRTUAL_GPU_TFLOPS = 80.0

    def __init__(self, **data):
        strategy = data.pop("pricing_strategy", None)
        super().__init__(**data)
        if strategy is None:
            from src.strategies.pricing.fixed_margin import FixedMarginPricing
            strategy = FixedMarginPricing()
        self._pricing_strategy = strategy

    @classmethod
    def with_devices(cls, identifier: str, devices: list[DeviceSpec], **kwargs) -> "DataCenter":
        return cls(
            id=identifier,
            name=kwargs.pop("name", identifier),
            total_compute=kwargs.pop("total_compute", sum(d.compute_tflops * d.quantity for d in devices) or 1),
            device_pool=devices,
            **kwargs,
        )

    @property
    def available_compute(self) -> float:
        return max(0.0, self.total_compute - self.used_compute)

    @property
    def available_bandwidth(self) -> float:
        return max(0.0, self.total_bandwidth - self.used_bandwidth)

    def used_device_count(self, model: str) -> int:
        return self._used_devices.get(model, 0)

    @staticmethod
    def _is_compute_device(device: DeviceSpec) -> bool:
        """Return whether a device can satisfy a task's GPU requirement.

        Configurations created by older simulators sometimes omit
        ``equipment_type`` or use a GPU model as the type marker.  The
        positive compute capacity is the reliable signal in those files.
        """
        equipment_type = str(device.equipment_type).strip().lower()
        model = str(device.model).strip().upper()
        return (
            equipment_type == "compute"
            or device.compute_tflops > 0
            or model.startswith(("GPU", "H100", "V100", "A100", "T4", "P100"))
        )

    def _gpu_capacity(self, model: str | None) -> tuple[list[DeviceSpec], int, str | None]:
        """Return compatible GPU inventory, capacity and reservation key.

        Task exports commonly use different GPU labels from the platform
        inventory. If the data center has compute capacity but no device
        inventory (as with older/custom configs), expose virtual 80-TFLOPS
        accelerator slots so the workload remains schedulable.
        """
        compute_devices = [d for d in self.device_pool if self._is_compute_device(d)]
        exact = [d for d in compute_devices if model and d.model == model]
        if exact:
            return exact, sum(d.quantity for d in exact), model
        if compute_devices:
            return compute_devices, sum(d.quantity for d in compute_devices), self._GENERIC_GPU_KEY
        virtual_capacity = max(1, int(self.total_compute // self._VIRTUAL_GPU_TFLOPS))
        return [], virtual_capacity, self._GENERIC_GPU_KEY

    def can_allocate(self, requirement: Union[Task, float], required_bandwidth: float = 0.0) -> bool:
        if not isinstance(requirement, Task):
            return self.available_compute >= requirement and self.available_bandwidth >= required_bandwidth
        bandwidth = requirement.required_bandwidth_mbps or requirement.compute_bandwidth_requirement()
        if self.available_compute < requirement.required_compute or self.available_bandwidth < bandwidth:
            return False
        if not requirement.required_gpu_count:
            return True
        model = requirement.required_gpu_type or requirement.gpu_type
        # Real workload exports often use placeholders such as MISC.  A
        # placeholder means "any compatible GPU", not a literal device model.
        # A task may name a GPU model (for example V100) that is not present in
        # the platform inventory (which may expose equivalent compute devices
        # as GPU-H100).  Treat an unknown model as an advisory label and use
        # the configured compute devices as the compatibility pool.  Cooling,
        # UPS and network devices must never satisfy a GPU requirement.
        candidates, capacity, reservation_key = self._gpu_capacity(model)
        if candidates:
            available = sum(d.quantity - self.used_device_count(d.model) for d in candidates)
        else:
            available = capacity
        if reservation_key == self._GENERIC_GPU_KEY:
            available -= self.used_device_count(self._GENERIC_GPU_KEY)
        return available >= requirement.required_gpu_count

    def allocate(self, requirement: Union[Task, float], required_bandwidth: float = 0.0) -> bool:
        if not self.can_allocate(requirement, required_bandwidth):
            raise ValueError("resource capacity is insufficient")
        if not isinstance(requirement, Task):
            self.used_compute += requirement
            self.used_bandwidth += required_bandwidth
            return True
        bandwidth = requirement.required_bandwidth_mbps or requirement.compute_bandwidth_requirement()
        self.used_compute += requirement.required_compute
        self.used_bandwidth += bandwidth
        if requirement.required_gpu_count:
            model = requirement.required_gpu_type or requirement.gpu_type
            _, _, reservation_key = self._gpu_capacity(model)
            self._used_devices[reservation_key] = self.used_device_count(reservation_key) + requirement.required_gpu_count
        return True

    def release(self, requirement: Union[Task, float], required_bandwidth: float = 0.0) -> bool:
        if not isinstance(requirement, Task):
            self.used_compute = max(0.0, self.used_compute - requirement)
            self.used_bandwidth = max(0.0, self.used_bandwidth - required_bandwidth)
            return True
        self.used_compute = max(0.0, self.used_compute - requirement.required_compute)
        self.used_bandwidth = max(0.0, self.used_bandwidth - requirement.required_bandwidth_mbps)
        if requirement.required_gpu_count:
            model = requirement.required_gpu_type or requirement.gpu_type
            _, _, reservation_key = self._gpu_capacity(model)
            self._used_devices[reservation_key] = max(
                0, self.used_device_count(reservation_key) - requirement.required_gpu_count
            )
        return True

    def total_power_mw(self, it_power_mw: float) -> float:
        return it_power_mw * self.pue

    def power_for_task_mw(self, task: Task, elapsed_seconds: float | None = None) -> float:
        """Estimate task power from repeating equipment telemetry.

        Runtime callers provide ``elapsed_seconds`` and receive the sample at
        that position in the repeating trace. Optimizers omit the time and use
        the complete trace average. Compute-device power is charged for the
        number of devices needed by the task; shared infrastructure is charged
        in proportion to the task's share of data-centre compute capacity.
        Curves and the legacy linear coefficient remain fallbacks for devices
        or centres without telemetry.
        """
        if not self.device_pool:
            return self.power_scale * self.total_power_mw(task.required_compute * self.power_per_tflops)
        utilization = min(1.0, max(0.0, task.required_compute / self.total_compute))
        if not any(device.power_trace for device in self.device_pool):
            equipment_kw = sum(
                device.power_kw_at(utilization) * device.quantity
                for device in self.device_pool
            )
            return self.power_scale * self.total_power_mw(equipment_kw / 1000.0)

        def sampled_power_kw(device: DeviceSpec) -> float:
            if not device.power_trace:
                return device.power_kw_at(utilization)
            if elapsed_seconds is None:
                return device.average_trace_power_kw()
            return device.power_kw_at_time(elapsed_seconds)

        equipment_kw = 0.0
        remaining_compute = task.required_compute
        remaining_explicit_devices = int(task.required_gpu_count or 0)
        for device in self.device_pool:
            if not self._is_compute_device(device):
                equipment_kw += sampled_power_kw(device) * device.quantity * utilization
                continue

            if device.compute_tflops > 0:
                compute_count = math.ceil(max(0.0, remaining_compute) / device.compute_tflops)
            else:
                compute_count = 0
            device_count = min(
                device.quantity,
                max(compute_count, remaining_explicit_devices),
            )
            equipment_kw += sampled_power_kw(device) * device_count
            remaining_compute = max(
                0.0,
                remaining_compute - device_count * device.compute_tflops,
            )
            remaining_explicit_devices = max(0, remaining_explicit_devices - device_count)
        return self.power_scale * self.total_power_mw(equipment_kw / 1000.0)

    def update_price(self, node_price_per_kwh: float) -> float:
        self.current_price = self._pricing_strategy.calculate_price(node_price_per_kwh, self)
        return self.current_price
