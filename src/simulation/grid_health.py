"""Composite grid-health scoring derived from physical operating metrics."""

from __future__ import annotations

from typing import Any


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


def calculate_grid_health(
    *,
    converged: bool | None,
    voltage: dict[str, Any],
    line: dict[str, Any],
    voltage_margin_pct: float | None,
    reserve_capacity_mw: float | None,
    total_load_mw: float | None,
) -> dict[str, Any]:
    """Return a 100-point score and independently inspectable sub-scores."""
    if converged is False:
        return {
            "score": 0.0,
            "level": "critical",
            "components": {"voltage": 0.0, "line": 0.0, "stability": 0.0, "reserve": 0.0},
        }

    min_voltage = voltage.get("min_voltage_pu")
    max_voltage = voltage.get("max_voltage_pu")
    violating_buses = int(voltage.get("violating_buses") or 0)
    if min_voltage is None or max_voltage is None:
        voltage_score = 70.0
    else:
        voltage_score = _clamp(
            100.0
            - 400.0 * max(0.0, 0.95 - float(min_voltage))
            - 250.0 * max(0.0, float(max_voltage) - 1.05)
            - 1.5 * violating_buses
        )

    max_loading = line.get("max_loading_pct")
    if max_loading is None:
        line_score = 70.0
    elif float(max_loading) <= 80.0:
        line_score = 100.0
    elif float(max_loading) <= 100.0:
        line_score = 100.0 - 1.25 * (float(max_loading) - 80.0)
    else:
        line_score = 75.0 - 1.3 * (float(max_loading) - 100.0)
    line_score = _clamp(line_score)

    stability_score = 70.0 if voltage_margin_pct is None else _clamp(60.0 + 2.0 * float(voltage_margin_pct))
    if reserve_capacity_mw is None or total_load_mw is None or float(total_load_mw) <= 0:
        reserve_score = 70.0
    else:
        reserve_score = _clamp(float(reserve_capacity_mw) / float(total_load_mw) / 0.20 * 100.0)

    score = round(
        0.35 * voltage_score
        + 0.35 * line_score
        + 0.20 * stability_score
        + 0.10 * reserve_score,
        2,
    )
    level = "healthy" if score >= 85.0 else "attention" if score >= 60.0 else "critical"
    return {
        "score": score,
        "level": level,
        "components": {
            "voltage": round(voltage_score, 2),
            "line": round(line_score, 2),
            "stability": round(stability_score, 2),
            "reserve": round(reserve_score, 2),
        },
    }
