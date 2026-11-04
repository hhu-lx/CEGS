import pytest

from src.simulation.grid_health import calculate_grid_health


def test_healthy_grid_scores_above_ninety():
    result = calculate_grid_health(
        converged=True,
        voltage={"min_voltage_pu": 0.98, "max_voltage_pu": 1.03, "violating_buses": 0},
        line={"max_loading_pct": 65.0},
        voltage_margin_pct=20.0,
        reserve_capacity_mw=1500.0,
        total_load_mw=6000.0,
    )

    assert result["score"] >= 90.0
    assert result["level"] == "healthy"


def test_typical_slight_voltage_violation_stays_above_seventy():
    result = calculate_grid_health(
        converged=True,
        voltage={"min_voltage_pu": 0.925, "max_voltage_pu": 1.064, "violating_buses": 10},
        line={"max_loading_pct": 80.0},
        voltage_margin_pct=15.0,
        reserve_capacity_mw=1657.0,
        total_load_mw=6300.0,
    )

    assert result["score"] >= 70.0
    assert result["level"] in {"healthy", "attention"}


def test_severe_undervoltage_and_overload_can_drop_below_sixty():
    result = calculate_grid_health(
        converged=True,
        voltage={"min_voltage_pu": 0.88, "max_voltage_pu": 1.06, "violating_buses": 12},
        line={"max_loading_pct": 135.39},
        voltage_margin_pct=5.0,
        reserve_capacity_mw=1657.0,
        total_load_mw=6300.0,
    )

    assert result["score"] == pytest.approx(52.17, abs=0.1)
    assert result["score"] < 60.0
    assert result["level"] == "critical"


def test_non_converged_grid_scores_zero():
    result = calculate_grid_health(
        converged=False,
        voltage={},
        line={},
        voltage_margin_pct=None,
        reserve_capacity_mw=None,
        total_load_mw=6300.0,
    )

    assert result["score"] == 0.0
    assert result["level"] == "critical"
