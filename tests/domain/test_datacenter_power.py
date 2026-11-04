from src.domain.datacenter import DataCenter
import pytest

from src.domain.device import DeviceSpec, PowerCurvePoint
from src.domain.task import Task


def test_data_center_power_uses_compute_and_cooling_curves():
    dc = DataCenter.with_devices("dc", [
        DeviceSpec(model="GPU", equipment_type="compute", quantity=2, compute_tflops=10,
                   idle_power_kw=100, rated_power_kw=200,
                   power_curve=[PowerCurvePoint(utilization=0, power_kw=100), PowerCurvePoint(utilization=1, power_kw=200)]),
        DeviceSpec(model="CH", equipment_type="cooling", quantity=1, compute_tflops=0,
                   idle_power_kw=20, rated_power_kw=100,
                   power_curve=[PowerCurvePoint(utilization=0, power_kw=20), PowerCurvePoint(utilization=1, power_kw=100)]),
    ], total_compute=20, pue=1.0)
    task = Task(user_id="u", task_type="general", compute_amount_tflop_hours=10, duration_hours=1)

    # 两块 GPU 各 150 kW，冷机 60 kW；设备曲线合计 360 kW = 0.36 MW。
    assert dc.power_for_task_mw(task) == 0.36


def test_data_center_power_prefers_repeating_traces_and_scales_device_count():
    dc = DataCenter.with_devices("dc", [
        DeviceSpec(
            model="GPU", equipment_type="compute", quantity=2,
            compute_tflops=10, idle_power_kw=50, rated_power_kw=250,
            power_curve=[
                PowerCurvePoint(utilization=0, power_kw=50),
                PowerCurvePoint(utilization=1, power_kw=250),
            ],
            power_trace=[
                {"time_s": 0, "power_kw": 100, "utilization": 0.5},
                {"time_s": 1, "power_kw": 200, "utilization": 1.0},
            ],
        ),
        DeviceSpec(
            model="CH", equipment_type="cooling", quantity=1,
            rated_power_kw=80,
            power_trace=[
                {"time_s": 0, "power_kw": 20, "utilization": 0.5},
                {"time_s": 1, "power_kw": 40, "utilization": 1.0},
            ],
        ),
    ], total_compute=20, pue=1.0)
    half_load = Task(user_id="u", task_type="general", required_compute=10, duration_hours=1)
    full_load = Task(user_id="u", task_type="general", required_compute=20, duration_hours=1)

    # 10 TFLOPS needs one GPU. Shared cooling is charged at 50%.
    assert dc.power_for_task_mw(half_load, elapsed_seconds=0) == pytest.approx(0.110)
    assert dc.power_for_task_mw(half_load, elapsed_seconds=1) == pytest.approx(0.220)
    # At two seconds the two-sample trace repeats from sample zero.
    assert dc.power_for_task_mw(half_load, elapsed_seconds=2) == pytest.approx(0.110)
    # 20 TFLOPS needs both GPUs and receives the full shared cooling load.
    assert dc.power_for_task_mw(full_load, elapsed_seconds=0) == pytest.approx(0.220)


def test_data_center_optimizer_power_uses_full_trace_average():
    dc = DataCenter.with_devices("dc", [
        DeviceSpec(
            model="GPU", equipment_type="compute", quantity=2,
            compute_tflops=10, rated_power_kw=250,
            power_trace=[
                {"time_s": 0, "power_kw": 100},
                {"time_s": 1, "power_kw": 200},
            ],
        ),
        DeviceSpec(
            model="UPS", equipment_type="power_distribution", quantity=1,
            rated_power_kw=80,
            power_trace=[
                {"time_s": 0, "power_kw": 20},
                {"time_s": 1, "power_kw": 40},
            ],
        ),
    ], total_compute=20, pue=1.0)
    task = Task(user_id="u", task_type="general", required_compute=10, duration_hours=1)

    # One GPU averages 150 kW; the task receives half of the 30 kW UPS average.
    assert dc.power_for_task_mw(task) == pytest.approx(0.165)
