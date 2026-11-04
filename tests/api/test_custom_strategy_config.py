import pytest

from src.api.frontend_routes import FrontendSession, _validated_custom_objective


def _pricing_periods():
    return {"periods": [{"start_hour": 0, "end_hour": 24, "price": 0.5}]}


def test_frontend_session_applies_parameterized_dispatch_and_pricing():
    session = FrontendSession()

    result = session.apply(
        dispatch_strategy="custom",
        pricing_strategy="custom",
        optimization_model="local",
        topology="IEEE 39节点系统",
        user_config=None,
        pricing=_pricing_periods(),
        files={},
        custom_dispatch={
            "name": "price_load_mix",
            "weights": {"price": 0.5, "load": 0.3, "carbon": 0.1, "latency": 0.1},
            "allow_cross_region": True,
        },
        custom_pricing={
            "name": "grid_responsive_price",
            "base_price": 0.45,
            "local_load_coefficient": 0.0002,
            "compute_load_coefficient": 0.002,
            "voltage_deviation_coefficient": 1.5,
            "minimum_price": 0.2,
            "maximum_price": 1.5,
        },
    )

    assert session.ui_config["scheduling"] == {
        "strategy": "custom_weighted",
        "settings": {
            "weights": result["configuration"]["custom_dispatch_strategy"]["weights"],
            "allow_cross_region": True,
        },
    }
    assert session.ui_config["electricity_pricing"]["mode"] == "custom"
    assert session.ui_config["electricity_pricing"]["parameters"]["base_price"] == 0.45


def test_frontend_session_rejects_unknown_custom_dispatch_weight():
    session = FrontendSession()

    with pytest.raises(ValueError, match="unknown weight"):
        session.apply(
            dispatch_strategy="custom",
            pricing_strategy="fixed_tou",
            optimization_model="local",
            topology="IEEE 39节点系统",
            user_config=None,
            pricing=_pricing_periods(),
            files={},
            custom_dispatch={"weights": {"price": 1, "luck": 1}},
            custom_pricing=None,
        )


def test_frontend_session_applies_safe_custom_optimization_objective():
    session = FrontendSession()
    weights = {
        "cost": 1.0,
        "carbon": 0.5,
        "delay": 0.2,
        "peak_shaving": 2.0,
        "renewable_curtailment": 3.0,
        "storage_degradation": 0.1,
    }

    result = session.apply(
        dispatch_strategy="lowest_price",
        pricing_strategy="marginal",
        optimization_model="global",
        objective_strategy="custom",
        topology="IEEE 39节点系统",
        user_config=None,
        pricing=_pricing_periods(),
        files={},
        custom_objective={"name": "custom_multi_objective", "weights": weights},
    )

    assert session.ui_config["optimization"]["objective"] == "weighted"
    assert session.ui_config["optimization"]["weights"] == weights
    assert result["configuration"]["custom_objective"]["weights"] == weights


def test_custom_objective_rejects_unknown_or_all_zero_weights():
    with pytest.raises(ValueError, match="unknown weight"):
        _validated_custom_objective({"weights": {"cost": 1, "luck": 2}})
    with pytest.raises(ValueError, match="at least one"):
        _validated_custom_objective({"weights": {"cost": 0, "carbon": 0}})


def test_heuristic_custom_objective_rejects_delay_weight():
    session = FrontendSession()

    with pytest.raises(ValueError, match="时延权重"):
        session.apply(
            dispatch_strategy="load_balance",
            pricing_strategy="marginal",
            optimization_model="heuristic",
            objective_strategy="custom",
            topology="IEEE 39节点系统",
            user_config=None,
            pricing=_pricing_periods(),
            files={},
            custom_objective={"weights": {"cost": 1.0, "delay": 0.2}},
        )
