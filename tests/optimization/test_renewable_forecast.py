import numpy as np

from src.optimization.renewable_forecast import ShortTermRenewableForecaster


def test_forecast_uses_only_history_before_current_index():
    forecaster = ShortTermRenewableForecaster(step_seconds=300)
    observations = [0.20, 0.22, 0.24, 0.95, 0.95]

    result = forecaster.forecast(
        observations,
        current_second=600,
        horizon_steps=3,
        kind="wind",
        capacity_mw=1300.0,
    )

    assert len(result) == 3
    assert result[0] < 0.50
    assert np.all(np.isfinite(result))


def test_pv_forecast_is_zero_at_night_and_nonnegative():
    forecaster = ShortTermRenewableForecaster(step_seconds=300)

    result = forecaster.forecast(
        [0.0, 0.0, 0.0],
        current_second=2 * 3600,
        horizon_steps=6,
        kind="pv",
        capacity_mw=2920.0,
    )

    assert len(result) == 6
    assert all(value == 0.0 for value in result)


def test_wind_forecast_respects_ramp_limit():
    forecaster = ShortTermRenewableForecaster(
        step_seconds=300,
        wind_ramp_mw_per_minute=4.0,
    )

    result = forecaster.forecast(
        [0.20, 0.21, 0.22],
        current_second=900,
        horizon_steps=4,
        kind="wind",
        capacity_mw=1300.0,
    )

    assert all(abs(result[i] - result[i - 1]) <= 20.0 + 1e-9 for i in range(1, len(result)))
