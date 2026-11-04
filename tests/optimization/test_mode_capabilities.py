import pytest

from src.optimization.mode_capabilities import (
    capabilities_for,
    normalise_frontend_selection,
)


def test_heuristic_exposes_dispatch_choices_and_excludes_delay_objective():
    capabilities = capabilities_for("heuristic")

    assert capabilities.fixed_dispatch is None
    assert capabilities.dispatch_strategies == (
        "lowest_price",
        "low_carbon",
        "custom",
    )
    assert capabilities.objectives == (
        "min_cost",
        "min_curtailment",
        "weighted",
        "custom",
    )


def test_local_exposes_all_dispatch_strategies_and_objectives():
    capabilities = capabilities_for("local")

    assert capabilities.fixed_dispatch is None
    assert capabilities.dispatch_strategies == (
        "lowest_price",
        "low_carbon",
        "custom",
    )
    assert capabilities.objectives == (
        "min_cost", "min_curtailment", "weighted", "custom",
    )


def test_global_marks_dispatch_as_joint_optimizer_managed():
    capabilities = capabilities_for("global")

    assert capabilities.fixed_dispatch == "optimizer_managed"
    assert capabilities.dispatch_strategies == ()
    assert capabilities.objectives == (
        "min_cost", "min_curtailment", "weighted", "custom",
    )


def test_normalisation_returns_effective_values_for_managed_modes():
    heuristic = normalise_frontend_selection("heuristic", "low_carbon", "min_cost")
    joint = normalise_frontend_selection("global", None, "weighted")

    assert heuristic.dispatch_strategy == "low_carbon"
    assert heuristic.dispatch_managed_by is None
    assert joint.dispatch_strategy == "optimizer_managed"
    assert joint.dispatch_managed_by == "joint_optimizer"


def test_normalisation_rejects_incompatible_objective_and_dispatch():
    with pytest.raises(ValueError, match="min_carbon"):
        normalise_frontend_selection("heuristic", None, "min_carbon")
    with pytest.raises(ValueError, match="Dispatch strategy"):
        normalise_frontend_selection("global", "custom", "min_cost")
    with pytest.raises(ValueError, match="dispatch strategy"):
        normalise_frontend_selection("local", "unknown", "min_cost")


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError, match="Unknown optimization model"):
        capabilities_for("unknown")
