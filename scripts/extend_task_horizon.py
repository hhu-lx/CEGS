"""Extend task arrival timestamps to a full simulation day.

The task types, power requirements, durations and wait limits are preserved.
Only the ordered ``submitted_at`` values are stretched to the requested
horizon, so the workload count is unchanged and the original CSV is backed up.
"""

from __future__ import annotations

import argparse
import csv
import shutil
from pathlib import Path


def extend_task_horizon(source: Path, *, horizon_seconds: float, end_margin_seconds: float) -> Path:
    with source.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    if "submitted_at" not in fieldnames or not rows:
        raise ValueError("task CSV must contain submitted_at and at least one task")

    values = []
    for row in rows:
        try:
            values.append(float(row.get("submitted_at", 0.0) or 0.0))
        except (TypeError, ValueError):
            values.append(0.0)
    order = sorted(range(len(rows)), key=lambda index: (values[index], index))
    last_input = max(values)
    target_last = max(0.0, float(horizon_seconds) - max(0.0, float(end_margin_seconds)))
    scale = target_last / last_input if last_input > 0 else 0.0
    for position, index in enumerate(order):
        value = values[index] * scale if scale else (
            target_last * position / max(1, len(order) - 1)
        )
        rows[index]["submitted_at"] = f"{value:.3f}"

    backup = source.with_name(f"{source.stem}.before_24h_20261022{source.suffix}")
    if not backup.exists():
        shutil.copy2(source, backup)
    temporary = source.with_suffix(source.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(source)
    print(f"updated={source} tasks={len(rows)} original_last={last_input:.3f}s new_last={target_last:.3f}s backup={backup}")
    return source


def main() -> None:
    parser = argparse.ArgumentParser(description="将任务提交时间扩展到完整仿真日")
    parser.add_argument("--source", type=Path, default=Path("config/task_data_completed.csv"))
    parser.add_argument("--horizon-seconds", type=float, default=86400.0)
    parser.add_argument("--end-margin-seconds", type=float, default=60.0)
    args = parser.parse_args()
    extend_task_horizon(
        args.source,
        horizon_seconds=args.horizon_seconds,
        end_margin_seconds=args.end_margin_seconds,
    )


if __name__ == "__main__":
    main()
