import json
from pathlib import Path

import pytest

from src.api.frontend_routes import FrontendSession, _parse_topology


def _platform_topology() -> dict:
    topology = json.loads(Path("config/topology_ieee39.json").read_text(encoding="utf-8"))
    topology["resource_mapping"] = {
        "pv_bus": 10,
        "wind_bus": 20,
        "load_buses": list(range(1, 30)),
    }
    return topology


def test_parse_topology_rejects_network_that_pandapower_cannot_build():
    topology = _platform_topology()
    topology["transformers"][0].pop("vn_hv_kv")

    with pytest.raises(ValueError, match="无法构建"):
        _parse_topology(json.dumps(topology).encode(), "broken.json")


def test_parse_topology_returns_normalized_generator_parameters():
    topology = _platform_topology()
    topology["generators"][0]["generator_type"] = "coal"

    parsed = _parse_topology(json.dumps(topology).encode(), "normalized.json")

    generator = parsed["generators"][0]
    assert generator["ramp_up_mw_per_hour"] == pytest.approx(0.125 * generator["max_p_mw"])
    assert generator["cost_linear_yuan_per_mwh"] > 0
    assert generator["parameter_sources"]["cost_linear_yuan_per_mwh"] == "default:coal"


def test_frontend_session_uses_uploaded_topology_and_mapping():
    topology = _platform_topology()
    topology["name"] = "session-test"
    session = FrontendSession()

    result = session.apply(
        dispatch_strategy="lowest_price",
        pricing_strategy="marginal",
        optimization_model="heuristic",
        objective_strategy="min_cost",
        topology="IEEE 39节点系统",
        user_config=None,
        pricing={},
        files={},
        uploaded_topology=topology,
    )

    assert result["configuration"]["topology_source"] == "user_upload"
    assert result["configuration"]["topology_summary"]["name"] == "session-test"
    assert session.ui_config["topology"] is topology
    assert session.ui_config["grid"]["pv_bus"] == 10
    assert result["configuration"]["generator_parameter_sources"]["gen_0"]["cost_linear_yuan_per_mwh"]


def test_frontend_session_rejects_resource_bus_missing_from_uploaded_topology():
    topology = json.loads(Path("tests/fixtures/topology_minimal.json").read_text(encoding="utf-8"))
    topology["resource_mapping"] = {"pv_bus": 1, "wind_bus": 2, "load_buses": [2]}

    with pytest.raises(ValueError, match=r"data_centers\[0\].grid_bus_id references unknown bus 3"):
        FrontendSession().apply(
            dispatch_strategy="lowest_price",
            pricing_strategy="marginal",
            optimization_model="heuristic",
            objective_strategy="min_cost",
            topology="IEEE 39节点系统",
            user_config=None,
            pricing={},
            files={},
            uploaded_topology=topology,
        )


def test_frontend_session_rejects_default_grid_bus_missing_from_uploaded_topology():
    topology = json.loads(Path("config/examples/custom_topology_test.json").read_text(encoding="utf-8"))
    topology.pop("resource_mapping")
    topology["buses"] = [bus for bus in topology["buses"] if bus["id"] != 20]
    topology["lines"] = [line for line in topology["lines"] if 20 not in (line["from_bus"], line["to_bus"])]
    topology["loads"] = [load for load in topology["loads"] if load["bus_id"] != 20]
    topology["renewables"] = [item for item in topology["renewables"] if item["bus_id"] != 20]

    with pytest.raises(ValueError, match="grid.wind_bus references unknown bus 20"):
        FrontendSession().apply(
            dispatch_strategy="lowest_price",
            pricing_strategy="marginal",
            optimization_model="heuristic",
            objective_strategy="min_cost",
            topology="IEEE 39节点系统",
            user_config=None,
            pricing={},
            files={},
            uploaded_topology=topology,
        )
