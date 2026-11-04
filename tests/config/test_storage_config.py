from pathlib import Path

from src.config.models import PlatformConfig


def test_platform_config_loads_storage_specs():
    config = PlatformConfig.from_yaml(Path("config/platform.yaml"))

    assert config.storages[0].id == "storage-1"
    assert config.storages[0].bus_id == 10
