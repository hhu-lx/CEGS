from pydantic import BaseModel, Field, model_validator


class EnergyStorage(BaseModel):
    """Grid-connected storage; positive power discharges into the grid."""

    id: str
    bus_id: int
    capacity_mwh: float = Field(gt=0)
    max_power_mw: float = Field(gt=0)
    initial_soc_mwh: float = Field(default=0, ge=0)
    min_soc_mwh: float = Field(default=0, ge=0)
    max_soc_mwh: float | None = Field(default=None, ge=0)
    charge_efficiency: float = Field(default=0.95, gt=0, le=1)
    discharge_efficiency: float = Field(default=0.95, gt=0, le=1)
    degradation_cost_per_mwh: float = Field(default=0, ge=0)
    soc_mwh: float | None = Field(default=None, ge=0)
    current_power_mw: float = 0.0
    throughput_mwh: float = 0.0

    @model_validator(mode="after")
    def initialise_soc(self) -> "EnergyStorage":
        if self.max_soc_mwh is None:
            self.max_soc_mwh = self.capacity_mwh
        if self.initial_soc_mwh > self.max_soc_mwh or self.min_soc_mwh > self.initial_soc_mwh:
            raise ValueError("storage SOC bounds are inconsistent")
        if self.soc_mwh is None:
            self.soc_mwh = self.initial_soc_mwh
        return self

    def apply_power(self, requested_mw: float, step_hours: float) -> float:
        if step_hours <= 0:
            raise ValueError("step_hours must be positive")
        requested_mw = max(-self.max_power_mw, min(self.max_power_mw, requested_mw))
        if requested_mw >= 0:
            available_energy = self.soc_mwh - self.min_soc_mwh
            actual = min(requested_mw, available_energy * self.discharge_efficiency / step_hours)
            self.soc_mwh -= actual * step_hours / self.discharge_efficiency
        else:
            remaining_energy = self.max_soc_mwh - self.soc_mwh
            actual = max(requested_mw, -remaining_energy / (self.charge_efficiency * step_hours))
            self.soc_mwh += -actual * step_hours * self.charge_efficiency
        self.current_power_mw = actual
        self.throughput_mwh += abs(actual) * step_hours
        return actual
