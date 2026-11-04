"""Generate a reproducible synthetic base-generation per-unit time series."""

from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


def generate_base_generation_pu(
    load: Iterable[float],
    photovoltaic: Iterable[float],
    wind: Iterable[float],
    *,
    smoothing_seconds: int = 300,
    lower_pu: float = 0.82,
    upper_pu: float = 0.98,
) -> np.ndarray:
    """Generate a baseline generation plan relative to nominal generators.

    The plan follows only the smoothed baseline load.  Renewable output and
    compute-task demand are deliberately excluded: they are real-time
    deviations handled by generator dispatch and storage.  ``photovoltaic``
    and ``wind`` remain in the signature for compatibility with existing data
    generation commands, but do not alter the baseline plan.
    """
    load_arr = np.asarray(list(load), dtype=np.float64)
    if len(load_arr) == 0:
        return np.array([], dtype=np.float64)
    if lower_pu <= 0 or upper_pu < lower_pu:
        raise ValueError("invalid generation per-unit bounds")

    baseline_demand = np.nan_to_num(load_arr, nan=0.0)
    window = max(1, int(smoothing_seconds))
    smoothed = pd.Series(baseline_demand).rolling(
        window, center=True, min_periods=1
    ).mean().to_numpy()
    low, high = np.quantile(smoothed, [0.05, 0.95])
    if high - low < 1e-12:
        return np.full(len(smoothed), (lower_pu + upper_pu) / 2.0)
    normalized = np.clip((smoothed - low) / (high - low), 0.0, 1.0)
    return lower_pu + normalized * (upper_pu - lower_pu)


def generate_base_generation_file(
    load_file: str,
    pv_file: str,
    wind_file: str,
    output_file: str,
    **kwargs,
) -> int:
    """Read one-column input files and write a one-column generation-pu CSV."""
    read = lambda path: pd.read_csv(path, header=None).iloc[:, 0].to_numpy(dtype=np.float64)
    profile = generate_base_generation_pu(read(load_file), read(pv_file), read(wind_file), **kwargs)
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    np.savetxt(output_file, profile, delimiter=",", fmt="%.8f")
    return len(profile)
