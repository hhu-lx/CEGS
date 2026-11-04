"""Extend a deterministic subset of task wait windows for rolling optimization."""

from hashlib import sha256
from pathlib import Path

import pandas as pd


path = Path(__file__).resolve().parents[1] / "config" / "task_data_completed.csv"
table = pd.read_csv(path)
column = "max_wait_seconds"
values = []
extended = 0
for index, row in table.iterrows():
    task_id = str(row.get("task_id", index))
    bucket = int(sha256(task_id.encode("utf-8")).hexdigest()[:8], 16) % 100
    old = float(row[column]) if pd.notna(row[column]) else 300.0
    if bucket < 60:
        new = min(1800.0, max(old, 900.0 + bucket / 59.0 * 900.0))
    else:
        new = old
    extended += int(new > old + 1e-9)
    values.append(round(new, 3))

table[column] = values
table.to_csv(path, index=False, encoding="utf-8")
print(
    f"rows={len(table)}, extended={extended}, "
    f"min={table[column].min():.3f}, median={table[column].median():.3f}, "
    f"max={table[column].max():.3f}"
)
