import pytest

from src.loaders.config_loader import build_data_centers, build_storages
from src.loaders.user_config_loader import validate_user_resources


def test_builds_multiple_custom_data_centers_and_storages():
    config = {
        "data_centers": [
            {"id": "DC-A", "name": "A", "region": "a", "grid_bus_id": 1,
             "total_compute": 10, "total_bandwidth": 100, "pue": 1.1,
             "device_pool": []},
            {"id": "DC-B", "name": "B", "region": "b", "grid_bus_id": 2,
             "total_compute": 20, "total_bandwidth": 200, "pue": 1.2,
             "device_pool": []},
        ],
        "storages": [
            {"id": "S1", "bus_id": 1, "capacity_mwh": 10, "max_power_mw": 2,
             "initial_soc_mwh": 5, "min_soc_mwh": 1, "charge_efficiency": 0.95,
             "discharge_efficiency": 0.95},
            {"id": "S2", "bus_id": 2, "capacity_mwh": 20, "max_power_mw": 4,
             "initial_soc_mwh": 10, "min_soc_mwh": 2, "charge_efficiency": 0.9,
             "discharge_efficiency": 0.9},
        ],
    }

    centers = build_data_centers(config)
    storages = build_storages(config)
    assert [center.id for center in centers] == ["DC-A", "DC-B"]
    assert [storage.id for storage in storages] == ["S1", "S2"]


def test_validate_user_resources_checks_bus_and_soc():
    with pytest.raises(ValueError, match=r"storages\[0\].bus_id"):
        validate_user_resources(
            {"data_centers": [], "storages": [{"id": "S", "bus_id": 99,
             "capacity_mwh": 10, "max_power_mw": 2, "initial_soc_mwh": 5,
             "min_soc_mwh": 1, "charge_efficiency": 0.9, "discharge_efficiency": 0.9}]},
            {"buses": [{"id": 1}]},
        )
