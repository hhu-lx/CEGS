from src.domain.device import DeviceSpec, PowerTracePoint


def test_device_power_trace_repeats_after_one_period():
    device = DeviceSpec(
        model="GPU", equipment_type="compute", quantity=1,
        rated_power_kw=0.7, idle_power_kw=0.35,
        power_trace=[
            PowerTracePoint(time_s=0, power_kw=0.35),
            PowerTracePoint(time_s=1, power_kw=0.55),
            PowerTracePoint(time_s=2, power_kw=0.70),
        ],
        period_seconds=3,
    )

    assert device.power_kw_at_time(0) == 0.35
    assert device.power_kw_at_time(2) == 0.70
    assert device.power_kw_at_time(3) == 0.35
    assert device.power_kw_at_time(5) == 0.70
