import json
from pathlib import Path

import pytest

from src.loaders.topology_loader import (
    build_pandapower_network,
    load_topology,
    normalise_generator_parameters,
    topology_grid_overrides,
    topology_summary,
    validate_topology,
)
from src.config.models import GeneratorDefaults
from src.infrastructure.pandapower_adapter import PandapowerAdapter


def test_load_and_build_json_topology():
    topology = load_topology("tests/fixtures/topology_minimal.json")
    network, bus_map = build_pandapower_network(topology)

    assert topology["name"] == "minimal"
    assert len(network.bus) == 2
    assert len(network.line) == 1
    assert len(network.gen) == 1
    assert bus_map[1] in network.bus.index


def test_topology_rejects_line_referencing_unknown_bus():
    topology = json.loads(Path("tests/fixtures/topology_minimal.json").read_text(encoding="utf-8"))
    topology["lines"][0]["to_bus"] = 99

    with pytest.raises(ValueError, match=r"lines\[0\].to_bus"):
        validate_topology(topology)


def test_topology_accepts_transformer_hv_and_lv_bus_references():
    topology = load_topology("tests/fixtures/topology_minimal.json")
    topology["transformers"] = [{
        "hv_bus": 1, "lv_bus": 2, "sn_mva": 50.0,
        "vn_hv_kv": 110.0, "vn_lv_kv": 110.0,
    }]
    validate_topology(topology)


def test_adapter_uses_user_topology_instead_of_default_case39():
    topology = load_topology("tests/fixtures/topology_minimal.json")
    adapter = PandapowerAdapter(topology=topology)

    assert adapter.topology["name"] == "minimal"
    assert len(adapter.network.bus) == 2


def test_adapter_prefers_inline_topology_over_configured_topology_file():
    topology = load_topology("tests/fixtures/topology_minimal.json")

    adapter = PandapowerAdapter(
        topology=topology,
        topology_file="config/topology_ieee39.json",
    )

    assert adapter.topology["name"] == "minimal"
    assert len(adapter.network.bus) == 2


def test_topology_resource_mapping_produces_grid_overrides_and_summary():
    topology = load_topology("tests/fixtures/topology_minimal.json")
    topology["resource_mapping"] = {
        "pv_bus": 2,
        "wind_bus": 1,
        "load_buses": [2],
    }

    validate_topology(topology)

    assert topology_grid_overrides(topology) == {
        "pv_bus": 2,
        "wind_bus": 1,
        "load_buses": [2],
        "base_mva": 100.0,
    }
    assert topology_summary(topology) == {
        "name": "minimal",
        "base_mva": 100.0,
        "bus_count": 2,
        "line_count": 1,
        "transformer_count": 0,
    }


def test_uploaded_topology_with_generators_enables_topology_generator_dispatch():
    topology = load_topology("config/examples/custom_topology_test.json")

    overrides = topology_grid_overrides(topology)

    assert "use_topology_generators" not in overrides


@pytest.mark.parametrize(
    ("mapping", "message"),
    [
        ({"pv_bus": 99}, "resource_mapping.pv_bus"),
        ({"wind_bus": 99}, "resource_mapping.wind_bus"),
        ({"load_buses": [2, 99]}, "resource_mapping.load_buses[1]"),
    ],
)
def test_topology_rejects_resource_mapping_referencing_unknown_bus(mapping, message):
    topology = load_topology("tests/fixtures/topology_minimal.json")
    topology["resource_mapping"] = mapping

    with pytest.raises(ValueError, match=message.replace("[", r"\[").replace("]", r"\]")):
        validate_topology(topology)


def test_generator_parameter_normalisation_preserves_user_values():
    generator = {
        "bus_id": 1, "p_mw": 30.0, "min_p_mw": 10.0, "max_p_mw": 80.0,
        "generator_type": "gas", "ramp_up_mw_per_hour": 12.0,
        "ramp_down_mw_per_hour": 11.0, "cost_linear_yuan_per_mwh": 321.0,
        "cost_quadratic_yuan_per_mw2h": 0.02, "emission_tco2_per_mwh": 0.31,
    }

    normalized = normalise_generator_parameters(generator, GeneratorDefaults())

    assert normalized["ramp_up_mw_per_hour"] == 12.0
    assert normalized["cost_linear_yuan_per_mwh"] == 321.0
    assert normalized["emission_tco2_per_mwh"] == 0.31
    assert normalized["parameter_sources"]["ramp_up_mw_per_hour"] == "user"
    assert normalized["parameter_sources"]["emission_tco2_per_mwh"] == "user"


def test_generator_parameter_normalisation_uses_documented_defaults():
    normalized = normalise_generator_parameters(
        {"bus_id": 1, "p_mw": 20.0, "min_p_mw": 0.0, "max_p_mw": 50.0},
        GeneratorDefaults(),
    )

    assert normalized["ramp_up_mw_per_hour"] == 6.25
    assert normalized["ramp_down_mw_per_hour"] == 6.25
    assert normalized["cost_linear_yuan_per_mwh"] > 0
    assert normalized["emission_tco2_per_mwh"] > 0
    assert normalized["parameter_sources"]["ramp_up_mw_per_hour"] == "default:0.125*max_p_mw"
    assert normalized["parameter_sources"]["cost_linear_yuan_per_mwh"] == "default:generic_thermal"


@pytest.mark.parametrize("bad_value", ["bad", float("nan"), float("inf")])
def test_generator_parameter_normalisation_rejects_non_finite_values(bad_value):
    with pytest.raises(ValueError, match="cost_linear_yuan_per_mwh"):
        normalise_generator_parameters(
            {
                "bus_id": 1, "min_p_mw": 0.0, "max_p_mw": 50.0,
                "cost_linear_yuan_per_mwh": bad_value,
            },
            GeneratorDefaults(),
        )


def test_generator_parameter_normalisation_rejects_inverted_bounds():
    with pytest.raises(ValueError, match="min_p_mw.*max_p_mw"):
        normalise_generator_parameters(
            {"bus_id": 1, "min_p_mw": 60.0, "max_p_mw": 50.0},
            GeneratorDefaults(),
        )
