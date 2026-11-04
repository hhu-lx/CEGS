from pathlib import Path

from src.config.models import PlatformConfig
from src.loaders.config_loader import build_data_centers, load_platform_config


def test_config_loads_the_example_platform_file():
    config = PlatformConfig.from_yaml(Path("config/platform.yaml"))

    assert config.simulation.time_unit == "seconds"
    assert config.simulation.step_seconds == 30
    assert config.simulation.stats_interval_seconds == 60
    assert config.simulation.renewable_optimization_interval_seconds == 900
    assert config.simulation.report_interval_seconds == 300
    assert config.simulation.cpf_interval_seconds == 900
    assert config.simulation.power_flow_interval_seconds == 900
    assert config.model_extra["grid"]["base_generation_capacity_mw"] == 7200.0
    assert config.model_extra["grid"]["load_capacity_mw"] == 6254.23
    assert config.model_extra["grid"]["use_topology_generators"] is False
    assert config.model_extra["scheduling"]["batch_interval_seconds"] == 5
    assert config.model_extra["scheduling"]["max_tasks_per_batch"] == 128
    assert config.optimization.global_time_limit_seconds == 2.0
    assert config.optimization.global_relative_mip_gap == 0.03
    assert config.optimization.load_balance_weight == 2.0
    assert config.optimization.minimum_active_center_tasks == 1
    assert config.synthetic_data.seed == 42


def test_runtime_loader_reads_device_curves_from_reference_table():
    data_centers = build_data_centers(load_platform_config())
    assert data_centers[0].device_pool
    assert {device.equipment_type for device in data_centers[0].device_pool} >= {
        "compute", "cooling", "power_distribution", "network"
    }
    assert data_centers[0].device_pool[0].power_kw_at(0.5) == 0.55
