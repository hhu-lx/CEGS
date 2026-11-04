"""Lightweight online short-term wind and PV forecasting."""

from __future__ import annotations

import math
from typing import Iterable

import numpy as np


class ShortTermRenewableForecaster:
    """Forecast only from observations available at the current timestamp."""

    def __init__(
        self,
        *,
        step_seconds: int = 300,
        observation_step_seconds: int | None = None,
        wind_ramp_mw_per_minute: float = 4.0,
        pv_ramp_mw_per_minute: float = 120.0,
    ):
        if step_seconds <= 0:
            raise ValueError("step_seconds must be positive")
        self.step_seconds = int(step_seconds)
        self.observation_step_seconds = int(observation_step_seconds or step_seconds)
        self.wind_ramp_mw_per_minute = max(0.0, float(wind_ramp_mw_per_minute))
        self.pv_ramp_mw_per_minute = max(0.0, float(pv_ramp_mw_per_minute))

    @staticmethod
    def _clean(values: Iterable[float]) -> np.ndarray:
        array = np.asarray(list(values), dtype=float)
        if array.size == 0:
            return np.zeros(1, dtype=float)
        array[~np.isfinite(array)] = 0.0
        return np.maximum(array, 0.0)

    @staticmethod
    def _daylight(second: float) -> float:
        hour = (float(second) % 86_400.0) / 3600.0
        return max(0.0, math.sin(math.pi * (hour - 5.5) / 13.0))

    def forecast(
        self,
        observations: Iterable[float],
        *,
        current_second: float,
        horizon_steps: int,
        kind: str,
        capacity_mw: float | None = None,
        values_are_pu: bool = False,
    ) -> list[float]:
        if horizon_steps <= 0:
            return []
        source = self._clean(observations)
        current_index = int(max(0.0, float(current_second)) // self.observation_step_seconds)
        history = source[: min(len(source), current_index + 1)]
        if history.size == 0:
            history = source[:1]
        history = history[-min(len(history), 60 * 60 // self.observation_step_seconds):]
        last = float(history[-1])
        window = history[-min(len(history), 12):]
        smooth = float(np.mean(window))
        if len(window) >= 2:
            trend = float(np.mean(np.diff(window)))
        else:
            trend = 0.0
        peak = float(np.max(history))
        kind = str(kind).lower()
        capacity = max(float(capacity_mw or 0.0), peak, last, 1e-9)
        if values_are_pu:
            capacity = 1.0

        if kind not in {"wind", "pv"}:
            raise ValueError("kind must be wind or pv")

        ramp_mw_per_minute = (
            self.wind_ramp_mw_per_minute
            if kind == "wind" else self.pv_ramp_mw_per_minute
        )
        ramp = ramp_mw_per_minute * self.step_seconds / 60.0
        if values_are_pu and capacity_mw:
            ramp /= float(capacity_mw)
        elif values_are_pu:
            ramp = min(1.0, ramp)

        forecast: list[float] = []
        previous = last
        for offset in range(horizon_steps):
            future_second = float(current_second) + offset * self.step_seconds
            daylight = self._daylight(future_second)
            estimate = smooth + trend * (offset + 1)
            if kind == "pv":
                if daylight <= 0.0:
                    estimate = 0.0
                elif self._daylight(current_second) <= 0.0:
                    # A physical daylight prior lets the model see sunrise
                    # without reading future rows from the observation file.
                    daylight_peak = max(peak, 0.75 if values_are_pu else capacity_mw * 0.75)
                    estimate = daylight_peak * daylight
                else:
                    estimate = max(0.0, estimate) * daylight / max(
                        self._daylight(current_second), 1e-6
                    )
            estimate = max(0.0, min(capacity, estimate))
            if ramp > 0.0:
                estimate = min(previous + ramp, max(previous - ramp, estimate))
            forecast.append(float(estimate))
            previous = estimate
        return forecast
