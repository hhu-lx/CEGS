import json
from pathlib import Path

import pytest

from src.domain.task import Task
from src.loaders.config_loader import build_data_centers
from src.loaders.user_config_loader import (
    load_user_config,
    merge_frontend_config,
    resolve_user_path,
    validate_frontend_user_config,
    validate_user_config,
)


def test_load_user_config_merges_file_and_defaults():
    defaults = {"simulation": {"step_seconds": 5, "stats_interval_seconds": 60}, "optimization": {"mode": "none"}}
    result = load_user_config(
        user_config_file="tests/fixtures/user_config_test.json",
        defaults=defaults,
    )

    assert result["simulation"]["step_seconds"] == 1
    assert result["simulation"]["stats_interval_seconds"] == 60
    assert result["optimization"]["mode"] == "joint"


def test_validate_user_config_rejects_invalid_mode_with_field_path():
    with pytest.raises(ValueError, match="optimization.mode"):
        validate_user_config({"optimization": {"mode": "unsupported"}})


def test_validate_user_config_rejects_incomplete_tariff():
    with pytest.raises(ValueError, match="pricing.periods"):
        validate_user_config({
            "pricing": {"mode": "fixed_tou", "periods": [
                {"start_hour": 0, "end_hour": 12, "price": 0.3},
                {"start_hour": 13, "end_hour": 24, "price": 0.8},
            ]}
        })


def test_resolve_user_path_rejects_parent_traversal():
    with pytest.raises(ValueError, match="outside allowed roots"):
        resolve_user_path("../secret.csv", [Path("config")])


def test_user_config_rejects_parent_traversal_in_data_sources():
    with pytest.raises(ValueError, match="data_sources.load_file"):
        validate_user_config({"data_sources": {"load_file": "uploads/../secret.csv"}})


@pytest.mark.parametrize("field", ["data_sources", "tasks", "pricing", "electricity_pricing", "topology"])
def test_frontend_user_config_rejects_duplicate_file_or_platform_inputs(field):
    with pytest.raises(ValueError, match=field):
        validate_frontend_user_config({field: {"file": "duplicate.csv"}})


def test_frontend_user_config_rejects_executable_objective_function():
    with pytest.raises(ValueError, match="objective_function"):
        validate_frontend_user_config({
            "optimization": {
                "mode": "joint",
                "objective_function": "untrusted_module:score",
            }
        })


def test_frontend_user_config_rejects_incomplete_resource_replacement():
    with pytest.raises(ValueError, match=r"data_centers\[0\].total_compute"):
        validate_frontend_user_config({"data_centers": [{"id": "CUSTOM", "name": "Custom", "region": "r", "grid_bus_id": 1}]})


def test_frontend_user_config_rejects_empty_data_center_replacement():
    with pytest.raises(ValueError, match="data_centers must contain at least one"):
        validate_frontend_user_config({"data_centers": []})


def test_frontend_merge_keeps_omitted_platform_sections_and_provenance():
    base = {
        "simulation": {"step_seconds": 10, "stats_interval_seconds": 300},
        "optimization": {"mode": "none", "objective": "cost"},
        "data_centers": [{"id": "DC1", "name": "Center", "region": "r", "grid_bus_id": 1, "total_compute": 250}],
        "storages": [{"id": "BAT1", "bus_id": 1, "capacity_mwh": 4, "max_power_mw": 1}],
    }

    effective, sources = merge_frontend_config(base, {"simulation": {"step_seconds": 5}}, {})

    assert effective["simulation"] == {"step_seconds": 5, "stats_interval_seconds": 300}
    assert effective["data_centers"] == [{"id": "DC1", "name": "Center", "region": "r", "grid_bus_id": 1, "total_compute": 250}]
    assert effective["storages"] == [{"id": "BAT1", "bus_id": 1, "capacity_mwh": 4, "max_power_mw": 1}]
    assert sources["data_centers"] == "platform_default"
    assert sources["simulation"] == "user_upload"


def test_frontend_merge_replaces_resource_collections_and_ui_controls_win():
    base = {
        "optimization": {"mode": "none", "objective": "cost", "weights": {"cost": 1, "emissions": 2}},
        "data_centers": [{"id": "DC1", "name": "Center", "region": "r", "grid_bus_id": 1, "total_compute": 250}],
        "storages": [{"id": "BAT1", "bus_id": 1, "capacity_mwh": 4, "max_power_mw": 1}],
    }
    user = {
        "optimization": {"mode": "global", "weights": {"emissions": 5}},
        "data_centers": [{"id": "CUSTOM", "name": "Custom", "region": "r", "grid_bus_id": 2, "total_compute": 777}],
        "storages": [],
    }

    effective, sources = merge_frontend_config(base, user, {"optimization": {"mode": "local"}})

    assert effective["optimization"] == {"mode": "local", "objective": "cost", "weights": {"cost": 1, "emissions": 5}}
    assert effective["data_centers"] == [{
        "id": "CUSTOM", "name": "Custom", "region": "r", "grid_bus_id": 2,
        "total_compute": 777, "device_pool": [], "power_per_tflops": 0.001,
    }]
    assert effective["storages"] == []
    assert sources["data_centers"] == "user_upload"
    assert sources["storages"] == "user_upload"


def test_frontend_empty_device_pool_inherits_platform_power_mapping_for_known_center():
    base = {"data_centers": [{
        "id": "DC1", "name": "Platform", "region": "r", "grid_bus_id": 3,
        "total_compute": 250, "power_per_tflops": 0.5,
        "device_pool": [{
            "model": "GPU-H100", "equipment_type": "compute", "quantity": 3,
            "compute_tflops": 80, "rated_power_kw": 0.7, "idle_power_kw": 0.35,
        }],
    }]}
    user = {"data_centers": [{
        "id": "DC1", "name": "Uploaded", "region": "new", "grid_bus_id": 16,
        "total_compute": 300, "total_bandwidth": 999, "power_per_tflops": 0.55,
        "device_pool": [],
    }]}

    effective, _ = merge_frontend_config(base, user, {})
    center = build_data_centers(effective)[0]
    power = center.power_for_task_mw(Task(user_id="u", task_type="general", required_compute=80, duration_hours=1))

    assert center.name == "Uploaded"
    assert center.grid_bus_id == 16
    assert center.total_compute == 300
    assert len(center.device_pool) == 1
    assert power < 1.0


def test_frontend_custom_center_without_devices_uses_safe_predefined_fallback():
    base = {"data_centers": [{
        "id": "DC1", "name": "Platform", "region": "r", "grid_bus_id": 3,
        "total_compute": 250, "power_per_tflops": 0.5, "device_pool": [],
    }]}
    user = {"data_centers": [{
        "id": "CUSTOM", "name": "Custom", "region": "r", "grid_bus_id": 2,
        "total_compute": 100, "device_pool": [],
    }]}

    effective, _ = merge_frontend_config(base, user, {})
    center = build_data_centers(effective)[0]
    power = center.power_for_task_mw(Task(user_id="u", task_type="general", required_compute=100, duration_hours=1))

    assert power == pytest.approx(0.1)
