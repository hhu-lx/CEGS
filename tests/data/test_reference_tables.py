from pathlib import Path

from src.data.reference_tables import (
    generate_reference_tables,
    load_equipment_power_curves,
    load_equipment_power_traces,
)


def test_generator_writes_reusable_equipment_curve_table():
    output_dir = Path("tests/data/generated_reference")
    paths = generate_reference_tables(output_dir)
    try:
        content = paths["equipment_power_curves"].read_text(encoding="utf-8")
        assert "cooling" in content
        assert "power_distribution" in content
        assert "network" in content
        curves = load_equipment_power_curves(paths["equipment_power_curves"])
        assert curves["Chiller-500kW"][-1].power_kw == 220.0
        traces = load_equipment_power_traces(paths["equipment_power_timeseries"])
        period, gpu_trace = traces["GPU-H100"]
        assert period == 240
        assert len(gpu_trace) == 240
        assert gpu_trace[0].power_kw == 68.6
        assert traces["Chiller-500kW"][1][0].power_kw == 18004.0359
    finally:
        for path in paths.values():
            path.unlink(missing_ok=True)
