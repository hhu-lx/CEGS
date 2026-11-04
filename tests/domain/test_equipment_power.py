from src.domain.device import DeviceSpec, PowerCurvePoint


def test_cooling_equipment_uses_piecewise_power_curve():
    chiller = DeviceSpec(
        model="CH-01", equipment_type="cooling", quantity=2,
        idle_power_kw=15, rated_power_kw=80,
        power_curve=[PowerCurvePoint(utilization=0, power_kw=15), PowerCurvePoint(utilization=1, power_kw=80)],
    )

    assert chiller.power_kw_at(0.5) == 47.5


def test_compute_device_keeps_compute_capacity():
    gpu = DeviceSpec(model="H100", equipment_type="compute", quantity=4, compute_tflops=60, idle_power_kw=0.35, rated_power_kw=0.7)

    assert gpu.compute_tflops == 60
