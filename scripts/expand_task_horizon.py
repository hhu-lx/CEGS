"""Expand the calibrated task workload to one day with daily peaks and valleys.

Rows are reused as templates with a deterministic daily arrival-rate profile,
preserving the original task type, compute, GPU, duration and wait-time
distributions. The source table is backed up before replacement.
"""

from __future__ import annotations

import argparse
import csv
import shutil
import random
import uuid
from pathlib import Path


def _arrival_rate_multiplier(hour: float) -> float:
    """Relative arrival rate: night valley, morning/evening peaks."""
    if hour < 6.0:
        return 0.65
    if hour < 10.0:
        return 1.35
    if hour < 17.0:
        return 0.90
    if hour < 21.0:
        return 1.35
    return 0.85


def expand_task_horizon(source: Path, *, horizon_seconds: float, cycle_seconds: float) -> None:
    with source.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fieldnames = list(reader.fieldnames or [])
        base_rows = list(reader)
    if not base_rows or "submitted_at" not in fieldnames or "task_id" not in fieldnames:
        raise ValueError("task CSV must contain task_id and submitted_at")

    base_rows.sort(key=lambda row: float(row.get("submitted_at", 0.0) or 0.0))
    source_times = [float(row.get("submitted_at", 0.0) or 0.0) for row in base_rows]
    intervals = [
        max(0.5, source_times[index + 1] - source_times[index])
        for index in range(len(source_times) - 1)
    ]
    fallback_interval = max(0.5, sum(intervals) / max(1, len(intervals)))
    if not intervals:
        intervals = [fallback_interval]

    expanded: list[dict[str, str]] = []
    namespace = uuid.uuid5(uuid.NAMESPACE_URL, "cesynergy-task-workload-2026-10-22")
    rng = random.Random("cesynergy-daily-workload-2026-10-22")
    submitted_at = 0.0
    position = 0
    while submitted_at <= float(horizon_seconds) - 60.0:
        source_row = base_rows[position % len(base_rows)]
        row = dict(source_row)
        row["submitted_at"] = f"{submitted_at:.3f}"
        if position >= len(base_rows):
            row["task_id"] = f"Task_{position}"
            row["A"] = str(uuid.uuid5(namespace, f"{position}:{source_row.get('task_id', '')}"))
        expanded.append(row)
        base_interval = intervals[position % len(intervals)] if intervals else fallback_interval
        hour = submitted_at / 3600.0
        multiplier = _arrival_rate_multiplier(hour)
        jitter = rng.uniform(0.90, 1.10)
        submitted_at += max(0.5, base_interval * jitter / multiplier)
        position += 1

    expanded.sort(key=lambda row: float(row.get("submitted_at", 0.0) or 0.0))
    backup = source.with_name(f"{source.stem}.before_expand_day_20261022{source.suffix}")
    if not backup.exists():
        shutil.copy2(source, backup)
    temporary = source.with_suffix(source.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(expanded)
    temporary.replace(source)
    print(
        f"updated={source} tasks={len(expanded)} "
        f"last={max(float(row['submitted_at']) for row in expanded):.3f}s backup={backup}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="将现有任务到达模式扩展到完整仿真日")
    parser.add_argument("--source", type=Path, default=Path("config/task_data_completed.csv"))
    parser.add_argument("--horizon-seconds", type=float, default=86400.0)
    parser.add_argument("--cycle-seconds", type=float, default=8400.0)
    args = parser.parse_args()
    expand_task_horizon(
        args.source,
        horizon_seconds=args.horizon_seconds,
        cycle_seconds=args.cycle_seconds,
    )


if __name__ == "__main__":
    main()
