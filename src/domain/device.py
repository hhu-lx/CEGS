from pydantic import BaseModel, Field, model_validator


class PowerCurvePoint(BaseModel):
    utilization: float = Field(ge=0, le=1)
    power_kw: float = Field(ge=0)


class PowerTracePoint(BaseModel):
    """One sample in a repeating one-second equipment power trace."""

    time_s: int = Field(ge=0)
    power_kw: float = Field(ge=0)
    utilization: float | None = Field(default=None, ge=0, le=1)


class DeviceSpec(BaseModel):
    """A data-centre device pool with a measured or representative power curve."""

    model: str
    equipment_type: str = "compute"  # compute, cooling, power_distribution, network
    quantity: int = Field(ge=0)
    compute_tflops: float = Field(default=0, ge=0)
    power_kw: float | None = Field(default=None, ge=0)  # legacy rated-power alias
    idle_power_kw: float | None = Field(default=None, ge=0)
    rated_power_kw: float | None = Field(default=None, gt=0)
    power_curve: list[PowerCurvePoint] = Field(default_factory=list)
    power_trace: list[PowerTracePoint] = Field(default_factory=list)
    period_seconds: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def normalise_power_fields(self) -> "DeviceSpec":
        if self.rated_power_kw is None:
            self.rated_power_kw = self.power_kw
        if self.rated_power_kw is None:
            raise ValueError("rated_power_kw or legacy power_kw is required")
        if self.idle_power_kw is None:
            self.idle_power_kw = self.rated_power_kw * 0.25
        self.power_curve.sort(key=lambda point: point.utilization)
        self.power_trace.sort(key=lambda point: point.time_s)
        if self.power_trace and self.period_seconds == 0:
            self.period_seconds = self.power_trace[-1].time_s + 1
        return self

    def power_kw_at(self, utilization: float) -> float:
        utilization = min(1.0, max(0.0, utilization))
        points = self.power_curve or [
            PowerCurvePoint(utilization=0, power_kw=self.idle_power_kw),
            PowerCurvePoint(utilization=1, power_kw=self.rated_power_kw),
        ]
        if utilization <= points[0].utilization:
            return points[0].power_kw
        for lower, upper in zip(points, points[1:]):
            if utilization <= upper.utilization:
                fraction = (utilization - lower.utilization) / (upper.utilization - lower.utilization)
                return lower.power_kw + fraction * (upper.power_kw - lower.power_kw)
        return points[-1].power_kw

    def power_kw_at_time(self, elapsed_seconds: float) -> float:
        """Read the repeating trace, linearly interpolating fractional seconds."""
        if not self.power_trace:
            return self.power_kw_at(1.0)
        period = self.period_seconds or (self.power_trace[-1].time_s + 1)
        position = elapsed_seconds % period
        if len(self.power_trace) == 1:
            return self.power_trace[0].power_kw
        lower = self.power_trace[0]
        for upper in self.power_trace[1:]:
            if position <= upper.time_s:
                span = upper.time_s - lower.time_s
                if span <= 0:
                    return upper.power_kw
                fraction = (position - lower.time_s) / span
                return lower.power_kw + fraction * (upper.power_kw - lower.power_kw)
            lower = upper
        # The final sample carries through to the period boundary.  The next
        # second wraps to sample zero, making the cycle deterministic.
        return self.power_trace[-1].power_kw

    def average_trace_power_kw(self) -> float:
        """Return the representative power used by scheduling optimizers."""
        if not self.power_trace:
            return self.power_kw_at(1.0)
        return sum(point.power_kw for point in self.power_trace) / len(self.power_trace)
