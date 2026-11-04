import pytest

from src.optimization.copt_optimizer import CoptOptimizer


def test_optimizer_maximizes_renewable_use_under_linear_grid_constraint():
    result = CoptOptimizer().optimize_renewable_dispatch(
        {"wind": 8.0, "pv": 4.0},
        linear_constraints=[
            {"coefficients": {"wind": 1.0, "pv": 1.0}, "rhs": 6.0},
        ],
    )

    assert result["status"] == "optimal"
    assert result["dispatched_mw"]["wind"] + result["dispatched_mw"]["pv"] == pytest.approx(6.0)
    assert result["curtailed_mw"]["wind"] + result["curtailed_mw"]["pv"] == pytest.approx(6.0)


def test_optimizer_keeps_all_renewables_when_grid_constraints_allow_them():
    result = CoptOptimizer().optimize_renewable_dispatch({"wind": 8.0, "pv": 4.0})

    assert result["status"] == "optimal"
    assert result["dispatched_mw"] == {"wind": pytest.approx(8.0), "pv": pytest.approx(4.0)}
    assert result["curtailed_mw"] == {"wind": pytest.approx(0.0), "pv": pytest.approx(0.0)}
