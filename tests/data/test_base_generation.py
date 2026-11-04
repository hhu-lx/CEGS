import numpy as np
import pytest

from src.data.base_generation import generate_base_generation_pu


def test_base_generation_is_smoothed_and_bounded():
    result = generate_base_generation_pu(
        [0.4, 0.8, 0.4], [0.1, 0.1, 0.1], [0.1, 0.1, 0.1],
        smoothing_seconds=1, lower_pu=0.8, upper_pu=1.0,
    )
    assert len(result) == 3
    assert np.all(result >= 0.8)
    assert np.all(result <= 1.0)


def test_base_generation_plan_is_independent_of_renewable_forecasts():
    load = [0.4, 0.8, 0.5, 0.7]

    without_renewables = generate_base_generation_pu(
        load, [0.0] * 4, [0.0] * 4,
        smoothing_seconds=1, lower_pu=0.8, upper_pu=1.0,
    )
    with_renewables = generate_base_generation_pu(
        load, [0.0, 0.7, 0.0, 0.5], [0.3, 0.0, 0.4, 0.0],
        smoothing_seconds=1, lower_pu=0.8, upper_pu=1.0,
    )

    assert with_renewables == pytest.approx(without_renewables)
