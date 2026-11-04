from src.domain.datacenter import DataCenter
from src.domain.device import DeviceSpec
from src.domain.task import Task


def test_data_center_rejects_unavailable_required_gpu():
    dc = DataCenter.with_devices(
        "dc1",
        [DeviceSpec(model="V100", quantity=1, compute_tflops=14, power_kw=300)],
    )
    task = Task(
        user_id="u1",
        task_type="ai_training",
        compute_amount_tflop_hours=12,
        duration_hours=1,
        required_gpu_count=2,
        required_gpu_type="V100",
    )

    assert dc.can_allocate(task) is False


def test_data_center_allocates_and_releases_task_resources():
    dc = DataCenter.with_devices(
        "dc1",
        [DeviceSpec(model="V100", quantity=2, compute_tflops=14, power_kw=300)],
        total_bandwidth=100,
    )
    task = Task(
        user_id="u1",
        task_type="ai_training",
        compute_amount_tflop_hours=12,
        duration_hours=1,
        data_size_gb=10,
        required_gpu_count=1,
        required_gpu_type="V100",
    )

    dc.allocate(task)
    assert dc.used_compute == 12
    assert dc.used_device_count("V100") == 1
    dc.release(task)
    assert dc.used_compute == 0
    assert dc.used_device_count("V100") == 0


def test_unknown_gpu_type_is_treated_as_generic_gpu_requirement():
    dc = DataCenter.with_devices(
        "dc1",
        [DeviceSpec(model="GPU-H100", quantity=2, compute_tflops=80, power_kw=300)],
    )
    task = Task(
        user_id="u1", task_type="ai_training", required_compute=1,
        duration_hours=1, required_gpu_count=1, required_gpu_type="MISC",
    )

    assert dc.can_allocate(task) is True
