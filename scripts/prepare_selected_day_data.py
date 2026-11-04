"""Prepare one realistic day of renewable/load data for the simulator."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(r"F:/算电协同原始数据")
CONFIG = ROOT / "config"
DAY_INDEX = 12  # day 13: balanced load, useful PV peak, moderate wind
LOAD_CAPACITY_MW = 6254.23
WIND_CAPACITY_MW = LOAD_CAPACITY_MW * 0.60
PV_CAPACITY_MW = LOAD_CAPACITY_MW * 0.70
BASE_CAPACITY_MW = 7200.0
FORECAST_RENEWABLE_MATCH = 0.85
FORECAST_SMOOTHING_SECONDS = 900


def read_month(path: Path) -> np.ndarray:
    # The supplied .csv files are BIFF8 workbooks with a misleading extension.
    table = pd.read_excel(path, header=None)
    values = table.iloc[1:, 1:].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    if values.shape[1] != 24 or values.shape[0] < 1:
        raise ValueError(f"{path} must contain a date column and 24 hourly columns")
    return np.nan_to_num(values, nan=0.0)


def interpolate_day(hourly: np.ndarray) -> np.ndarray:
    hourly = np.asarray(hourly, dtype=float)
    result = np.empty(24 * 3600, dtype=float)
    for hour in range(24):
        start = float(hourly[hour])
        end = float(hourly[(hour + 1) % 24])
        result[hour * 3600 : (hour + 1) * 3600] = np.linspace(
            start, end, 3600, endpoint=False
        )
    return result


def add_smooth_wind_variability(profile: np.ndarray, capacity_mw: float) -> np.ndarray:
    """Add slow, correlated wind variation without one-second jumps."""
    rng = np.random.default_rng(20261029)
    knot_step = 300
    knot_count = int(np.ceil(len(profile) / knot_step)) + 1
    noise = rng.normal(0.0, 1.0, knot_count)
    noise = np.convolve(noise, np.ones(5) / 5.0, mode="same")
    noise = noise[: int(np.ceil(len(profile) / knot_step)) + 1]
    noise = np.interp(np.arange(len(profile)), np.arange(len(noise)) * knot_step, noise)
    # 8% of installed capacity is enough to distinguish forecast/dispatch
    # behaviour while remaining a gradual physical fluctuation.
    varied = np.maximum(0.0, profile + noise * capacity_mw * 0.08)
    # Enforce a continuous ramp limit of 5% of capacity per 10 minutes.
    max_step = capacity_mw * 0.05 / 600.0
    for index in range(1, len(varied)):
        delta = varied[index] - varied[index - 1]
        varied[index] = varied[index - 1] + np.clip(delta, -max_step, max_step)
    return varied


def write_series(path: Path, values: np.ndarray) -> None:
    np.savetxt(path, np.asarray(values, dtype=float), delimiter=",", fmt="%.8f")


def main() -> None:
    load_month = read_month(SOURCE / "use.xlsx")
    wind_month = read_month(SOURCE / "wind.csv")
    pv_month = read_month(SOURCE / "sun.csv")
    if not (load_month.shape == wind_month.shape == pv_month.shape):
        raise ValueError("load, wind and PV source tables must have the same shape")

    load_h = load_month[DAY_INDEX]
    wind_h = wind_month[DAY_INDEX]
    pv_h = pv_month[DAY_INDEX]
    load_pu = interpolate_day(load_h)
    wind_pu = interpolate_day(wind_h)
    pv_pu = interpolate_day(pv_h)
    wind_mw = add_smooth_wind_variability(wind_pu * WIND_CAPACITY_MW, WIND_CAPACITY_MW)
    wind_pu = wind_mw / WIND_CAPACITY_MW

    # Aggregate profiles remain per-unit for generic topologies.
    write_series(CONFIG / "use_second.csv", load_pu)
    write_series(CONFIG / "wind_second.csv", wind_pu)
    write_series(CONFIG / "sun_second.csv", pv_pu)

    # Topology-bound node profiles are physical MW and are split explicitly.
    write_series(CONFIG / "wind_bus20_mw_second.csv", wind_mw * 0.50)
    write_series(CONFIG / "wind_bus3_mw_second.csv", wind_mw * 0.50)
    write_series(CONFIG / "pv_bus10_mw_second.csv", pv_pu * PV_CAPACITY_MW * 0.30)
    write_series(CONFIG / "pv_bus16_mw_second.csv", pv_pu * PV_CAPACITY_MW * 0.70)

    # Build the conventional plan from a smoothed, deliberately imperfect
    # renewable forecast. Actual wind/PV later use the perturbed profiles, so
    # the difference produces realistic curtailment instead of full matching.
    reference_load = max(float(load_pu.mean()), 1e-9)
    load_mw = LOAD_CAPACITY_MW * load_pu / reference_load
    smoothed = pd.Series(load_mw).rolling(300, center=True, min_periods=1).mean().to_numpy()
    renewable_actual_mw = wind_mw + pv_pu * PV_CAPACITY_MW
    renewable_forecast_mw = pd.Series(renewable_actual_mw).rolling(
        FORECAST_SMOOTHING_SECONDS, center=True, min_periods=1
    ).mean().to_numpy() * FORECAST_RENEWABLE_MATCH
    plan_mw = np.maximum(0.0, smoothed - renewable_forecast_mw)
    base_pu = np.clip(plan_mw / BASE_CAPACITY_MW, 0.0, 1.0)
    write_series(CONFIG / "base_generation_pu_second.csv", base_pu)

    print(f"selected_day={DAY_INDEX + 1}")
    print(f"load_mean_pu={load_h.mean():.6f}, load_peak_pu={load_h.max():.6f}")
    print(f"wind_capacity_mw={WIND_CAPACITY_MW:.3f}, pv_capacity_mw={PV_CAPACITY_MW:.3f}")
    print(f"wind_peak_mw={(wind_h.max() * WIND_CAPACITY_MW):.3f}, pv_peak_mw={(pv_h.max() * PV_CAPACITY_MW):.3f}")
    print(
        f"forecast_renewable_match={FORECAST_RENEWABLE_MATCH:.2f}, "
        f"forecast_smoothing_seconds={FORECAST_SMOOTHING_SECONDS}, rows={len(load_pu)}"
    )


if __name__ == "__main__":
    main()
