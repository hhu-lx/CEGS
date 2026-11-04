from src.loaders.config_loader import load_platform_config
from src.loaders.user_config_loader import load_user_config
from src.simulation.engine import SimulationEngine


def test_example_json_loads_with_three_centers_and_one_storage():
    config = load_user_config(user_config_file="config/user_config.example.json")

    assert config["optimization"]["mode"] == "none"
    assert len(config["data_centers"]) == 3
    assert len(config["storages"]) == 1


def test_legacy_yaml_still_loads():
    config = load_platform_config("config/platform.yaml")

    assert config["optimization"]["mode"] in {"none", "hierarchical", "joint"}
    assert len(config["data_centers"]) == 3
