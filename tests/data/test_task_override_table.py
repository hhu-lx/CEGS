import pandas as pd
from pathlib import Path

from src.data.task_override_table import create_task_override_table, generate_realistic_task_profile
from src.loaders.excel_loader import ExcelTaskLoader


def test_override_table_preserves_source_rows_and_adds_generated_fields():
    source = Path("config/_test_tasks_source.csv")
    output = Path("config/_test_tasks_completed.csv")
    pd.DataFrame([
        {
            "A": "job-1", "B": "AI_TRAINING", "C": "1", "D": "Terminated",
            "E": "0", "F": "3600", "G": "600", "H": "29.3", "I": "50", "J": "MISC", "算力消耗": "3000",
            "user_specified_data_center": "DC2",
        }
    ]).to_csv(source, index=False)

    result = create_task_override_table(source, output, seed=7)
    table = pd.read_csv(result, dtype=str)

    assert table.loc[0, "A"] == "job-1"
    assert table.loc[0, "user_specified_data_center"] == "DC2"
    assert table.loc[0, "data_size_gb"] != ""
    assert table.loc[0, "required_cpu_cores"] != ""
    assert "task_id" in table.columns
    loaded = ExcelTaskLoader(str(source)).load_tasks()
    assert loaded[0].user_specified_data_center == "DC2"
    completed_loaded = ExcelTaskLoader(str(output)).load_tasks()
    assert completed_loaded[0].data_size_gb == float(table.loc[0, "data_size_gb"])
    source.unlink(missing_ok=True)
    output.unlink(missing_ok=True)


def test_realistic_task_profile_has_bounded_durations_and_distinct_peak_periods():
    profile = generate_realistic_task_profile(600, seed=42)

    first_minute = sum(0 <= row["submitted_at"] < 60 for row in profile)
    normal_minute = sum(600 <= row["submitted_at"] < 660 for row in profile)
    peak_minute = sum(720 <= row["submitted_at"] < 780 for row in profile)

    assert profile[0]["submitted_at"] == 0.0
    assert all(left["submitted_at"] < right["submitted_at"] for left, right in zip(profile, profile[1:]))
    assert 8 <= first_minute <= 16
    assert peak_minute >= normal_minute * 1.5


def test_generated_override_table_limits_exclusive_gpu_share_and_task_duration():
    source = Path("config/_test_profile_source.csv")
    output = Path("config/_test_profile_completed.csv")
    rows = []
    for index in range(120):
        rows.append({
            "A": f"job-{index}", "B": "AI_TRAINING", "C": "1", "D": "Terminated",
            "E": str(index), "F": str(index + 500), "G": "600", "H": "29.3",
            "I": "100", "J": "MISC", "算力消耗": "3000",
        })
    pd.DataFrame(rows).to_csv(source, index=False)

    create_task_override_table(source, output, seed=42)
    table = pd.read_csv(output)

    gpu_share = (table["required_gpu_count"] > 0).mean()
    assert 0.10 <= gpu_share <= 0.30
    assert table["duration_seconds"].between(60, 240).all()
    assert table["max_wait_seconds"].between(90, 360).all()
    assert table["submitted_at"].between(0, 7200).all()
    source.unlink(missing_ok=True)
    output.unlink(missing_ok=True)
