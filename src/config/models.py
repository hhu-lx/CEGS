from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from src.optimization.mode_capabilities import COMPREHENSIVE_OBJECTIVE_WEIGHTS


class SimulationConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    time_unit: Literal["milliseconds", "seconds", "minutes", "hours"] = "seconds"
    step_seconds: float = Field(default=5.0, gt=0)
    duration_hours: float = Field(default=24.0, gt=0)
    stats_interval_seconds: int = Field(default=1, gt=0)
    renewable_optimization_interval_seconds: int = Field(default=5, gt=0)
    report_interval_seconds: int = Field(default=5, gt=0)
    cpf_interval_seconds: int = Field(default=30, gt=0)
    power_flow_interval_seconds: int = Field(default=300, gt=0)
    time_scale: float = Field(default=1.0, ge=0)


class SyntheticDataConfig(BaseModel):
    seed: int = 42


class StorageConfig(BaseModel):
    id: str
    bus_id: int
    capacity_mwh: float = Field(gt=0)
    max_power_mw: float = Field(gt=0)
    initial_soc_mwh: float = Field(ge=0)
    min_soc_mwh: float = Field(default=0, ge=0)
    charge_efficiency: float = Field(default=0.95, gt=0, le=1)
    discharge_efficiency: float = Field(default=0.95, gt=0, le=1)
    degradation_cost_per_mwh: float = Field(default=0, ge=0)


def _generator_profiles() -> dict[str, dict[str, float]]:
    """Documented fallback coefficients for user topologies.

    Values are platform assumptions rather than inferred plant data.  The
    normalized topology records the selected row in ``parameter_sources``.
    """
    return {
        "coal": {
            "cost_linear_yuan_per_mwh": 280.0,
            "cost_quadratic_yuan_per_mw2h": 0.010,
            "emission_tco2_per_mwh": 0.82,
        },
        "gas": {
            "cost_linear_yuan_per_mwh": 420.0,
            "cost_quadratic_yuan_per_mw2h": 0.008,
            "emission_tco2_per_mwh": 0.42,
        },
        "hydro": {
            "cost_linear_yuan_per_mwh": 80.0,
            "cost_quadratic_yuan_per_mw2h": 0.002,
            "emission_tco2_per_mwh": 0.02,
        },
        "nuclear": {
            "cost_linear_yuan_per_mwh": 180.0,
            "cost_quadratic_yuan_per_mw2h": 0.004,
            "emission_tco2_per_mwh": 0.012,
        },
        "generic_thermal": {
            "cost_linear_yuan_per_mwh": 350.0,
            "cost_quadratic_yuan_per_mw2h": 0.010,
            "emission_tco2_per_mwh": 0.70,
        },
    }


class GeneratorDefaults(BaseModel):
    """Fallback assumptions used to normalize conventional generators."""

    # Default thermal-unit ramp capability: 12.5% of nameplate per hour.
    ramp_fraction_per_hour: float = Field(default=0.125, gt=0)
    profiles: dict[str, dict[str, float]] = Field(default_factory=_generator_profiles)


class OptimizationConfig(BaseModel):
    enabled: bool = True
    mode: Literal["none", "hierarchical", "joint", "local", "global"] = "hierarchical"
    objective: Literal[
        "min_cost", "min_carbon", "min_delay", "min_curtailment",
        "peak_shaving", "weighted",
    ] = "min_cost"
    load_balance_weight: float = Field(default=1.0, ge=0)
    minimum_active_center_tasks: int = Field(default=1, ge=0)
    task_batch_interval_seconds: float = Field(default=300.0, gt=0)
    # Global coordination is a mixed-integer model.  A bounded solve returns
    # the best feasible schedule found so the real-time simulation cannot be
    # stalled while COPT proves the last fraction of a percent optimality.
    global_time_limit_seconds: float = Field(default=2.0, gt=0)
    global_relative_mip_gap: float = Field(default=0.03, ge=0, le=1)
    weights: dict[str, float] = Field(
        default_factory=lambda: dict(COMPREHENSIVE_OBJECTIVE_WEIGHTS)
    )
    objective_function: str | None = None


class PlatformConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    simulation: SimulationConfig = Field(default_factory=SimulationConfig)
    synthetic_data: SyntheticDataConfig = Field(default_factory=SyntheticDataConfig)
    storages: list[StorageConfig] = Field(default_factory=list)
    optimization: OptimizationConfig = Field(default_factory=OptimizationConfig)

    @classmethod
    def from_yaml(cls, path: Path) -> "PlatformConfig":
        with path.open(encoding="utf-8") as source:
            return cls.model_validate(yaml.safe_load(source) or {})
