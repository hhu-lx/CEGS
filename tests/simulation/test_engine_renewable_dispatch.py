import pytest

from src.simulation.engine import SimulationEngine


class FakeRenewableGrid:
    def __init__(self):
        self.dispatch = {"wind": 8.0, "pv": 4.0}
        self.heuristic_called = False
        self.power_flow_calls = 0

    def get_renewable_dispatch_summary(self):
        return {
            "wind": {"available_mw": 8.0, "dispatched_mw": self.dispatch["wind"], "curtailed_mw": 8.0 - self.dispatch["wind"]},
            "pv": {"available_mw": 4.0, "dispatched_mw": self.dispatch["pv"], "curtailed_mw": 4.0 - self.dispatch["pv"]},
        }

    def apply_heuristic_renewable_curtailment(self):
        self.heuristic_called = True
        self.dispatch = {"wind": 4.0, "pv": 2.0}
        return {"status": "curtailed", "dispatch_factor": 0.5}

    def optimize_renewable_grid_constraints(self):
        return [{"coefficients": {"wind": 1.0, "pv": 1.0}, "rhs": 6.0}]

    def apply_renewable_dispatch(self, dispatch):
        self.dispatch = dispatch

    def run_power_flow(self):
        self.power_flow_calls += 1

    def get_operating_constraint_snapshot(self):
        return {"feasible": True}

    def get_renewable_absorption_limit_mw(self):
        return 12.0


def _engine_for_dispatch(mode):
    engine = object.__new__(SimulationEngine)
    engine.pp_adapter = FakeRenewableGrid()
    engine.optimization_config = {"enabled": mode != "none", "mode": mode}
    engine.step_seconds = 3600
    engine.renewable_energy_mwh = {
        source: {"available": 0.0, "consumed": 0.0, "curtailed": 0.0}
        for source in ("wind", "pv")
    }
    return engine


def test_heuristic_mode_uses_grid_feedback_and_counts_curtailed_energy():
    engine = _engine_for_dispatch("none")

    SimulationEngine._dispatch_renewables(engine)

    assert engine.pp_adapter.heuristic_called
    assert engine.renewable_energy_mwh["wind"] == {"available": 8.0, "consumed": 4.0, "curtailed": 4.0}
    assert engine.renewable_energy_mwh["pv"] == {"available": 4.0, "consumed": 2.0, "curtailed": 2.0}


@pytest.mark.parametrize("mode", ["hierarchical", "joint"])
def test_optimization_modes_dispatch_renewables_inside_copt_model(mode):
    engine = _engine_for_dispatch(mode)

    SimulationEngine._dispatch_renewables(engine)

    assert engine.renewable_dispatch_result["status"] == "optimized"
    assert sum(engine.pp_adapter.dispatch.values()) == pytest.approx(6.0)
    assert engine.renewable_energy_mwh["wind"]["available"] == pytest.approx(8.0)
    assert engine.renewable_energy_mwh["pv"]["available"] == pytest.approx(4.0)


def test_reused_dispatch_scales_new_availability_by_last_optimized_ratio():
    engine = _engine_for_dispatch("hierarchical")
    engine._renewable_dispatch_factors = {"wind": 0.5, "pv": 0.25}

    SimulationEngine._reuse_renewable_dispatch(engine)

    assert engine.pp_adapter.dispatch == {"wind": pytest.approx(4.0), "pv": pytest.approx(1.0)}
    assert engine.renewable_energy_mwh["wind"] == {
        "available": pytest.approx(8.0),
        "consumed": pytest.approx(4.0),
        "curtailed": pytest.approx(4.0),
    }
    assert engine.renewable_energy_mwh["pv"] == {
        "available": pytest.approx(4.0),
        "consumed": pytest.approx(1.0),
        "curtailed": pytest.approx(3.0),
    }
    assert engine.pp_adapter.power_flow_calls == 0


def test_reused_dispatch_clamps_previous_ratio_to_current_absorption_limit():
    engine = _engine_for_dispatch("hierarchical")
    engine._renewable_dispatch_factors = {"wind": 0.5, "pv": 0.25}
    engine.pp_adapter.get_renewable_absorption_limit_mw = lambda: 3.0

    SimulationEngine._reuse_renewable_dispatch(engine)

    assert engine.pp_adapter.dispatch == {"wind": pytest.approx(2.4), "pv": pytest.approx(0.6)}
