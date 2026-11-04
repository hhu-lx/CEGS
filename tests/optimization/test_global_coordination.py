from src.optimization.global_coordination import GlobalCoordinationOptimizer
from src.optimization.joint_coordination import JointCoordinationOptimizer


def test_global_policy_adds_storage_and_peak_shaving_terms():
    objective, weights = GlobalCoordinationOptimizer.prepare_objective(
        "min_cost", {"cost": 1.0}
    )

    assert objective == "weighted"
    assert weights["cost"] == 1.0
    assert weights["peak_shaving"] > 0.0
    assert weights["storage_degradation"] > 0.0
    assert weights["renewable_curtailment"] > 0.0


def test_global_policy_keeps_explicit_weighted_values():
    objective, weights = GlobalCoordinationOptimizer.prepare_objective(
        "weighted", {"cost": 2.0, "delay": 0.4}
    )

    assert objective == "weighted"
    assert weights["cost"] == 2.0
    assert weights["delay"] == 0.4
    assert weights["peak_shaving"] > 0.0
    assert weights["storage_degradation"] > 0.0


def test_global_adapter_forces_terminal_soc_reserve(monkeypatch):
    captured = {}

    def fake_solve(self, *args, **kwargs):
        captured.update(kwargs)
        return "sentinel"

    monkeypatch.setattr(JointCoordinationOptimizer, "solve", fake_solve)
    result = GlobalCoordinationOptimizer().solve(
        [], [], None, objective="min_cost", weights={},
        latency_ms={}, carbon_intensity={},
    )

    assert result == "sentinel"
    assert captured["maintain_terminal_soc"] is True
    assert captured["objective"] == "weighted"
