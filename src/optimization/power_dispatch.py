"""Strict rolling power dispatch for generators, renewables and storage."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Iterable

import coptpy as cp


@dataclass(frozen=True)
class GeneratorDispatchInput:
    id: str
    bus_id: int
    min_mw: float
    max_mw: float
    initial_mw: float
    ramp_up_mw_per_hour: float
    ramp_down_mw_per_hour: float
    cost_linear_yuan_per_mwh: float
    cost_quadratic_yuan_per_mw2h: float
    emission_tco2_per_mwh: float
    reference_mw: list[float] = field(default_factory=list)


@dataclass(frozen=True)
class RenewableForecast:
    id: str
    bus_id: int
    available_mw: list[float]


@dataclass(frozen=True)
class StorageDispatchInput:
    id: str
    bus_id: int
    initial_soc_mwh: float
    min_soc_mwh: float
    max_soc_mwh: float
    max_power_mw: float
    charge_efficiency: float = 0.95
    discharge_efficiency: float = 0.95
    degradation_cost_per_mwh: float = 0.0
    terminal_soc_mwh: float | None = None
    initial_power_mw: float = 0.0


@dataclass(frozen=True)
class PowerDispatchProblem:
    load_mw: list[float]
    # Predetermined injections (for example, the data-driven conventional
    # plan after renewable-first balancing) that participate in the balance
    # but are not optimization decision variables.
    fixed_generation_mw: list[float] = field(default_factory=list)
    generators: list[GeneratorDispatchInput] = field(default_factory=list)
    renewables: list[RenewableForecast] = field(default_factory=list)
    storages: list[StorageDispatchInput] = field(default_factory=list)
    objective: str = "min_cost"
    objective_weights: dict[str, float] = field(default_factory=dict)
    electricity_prices: list[float] = field(default_factory=list)
    horizon_hours: int = 24
    step_hours: float = 1.0
    control_interval_hours: float | None = None
    start_second: float = 0.0
    forecast_fill: str = "native"
    external_grid_max_import_mw: float = 0.0
    external_grid_max_export_mw: float = 0.0


@dataclass(frozen=True)
class PowerDispatchResult:
    status: str
    objective_value: float | None
    generator_mw: dict[str, list[float]]
    renewable_dispatched_mw: dict[str, list[float]]
    renewable_curtailed_mw: dict[str, list[float]]
    storage_power_mw: dict[str, list[float]]
    storage_soc_mwh: dict[str, list[float]]
    objective_components: dict[str, dict[str, float]]
    strictly_feasible: bool
    forecast_fill: str
    external_grid_mw: list[float] = field(default_factory=list)


def _finite_nonnegative(values: Iterable[float], field_name: str) -> list[float]:
    result: list[float] = []
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name} must contain finite non-negative values") from exc
        if not math.isfinite(number) or number < 0:
            raise ValueError(f"{field_name} must contain finite non-negative values")
        result.append(number)
    if not result:
        raise ValueError(f"{field_name} must not be empty")
    return result


def _expand(values: list[float], length: int) -> tuple[list[float], bool]:
    if len(values) >= length:
        return values[:length], False
    return [values[index % len(values)] for index in range(length)], True


def electricity_price_factors(
    prices: list[float], horizon: int
) -> tuple[list[float], bool]:
    """Return tariff factors; one is the neutral fallback when no tariff exists."""
    if not prices:
        return [1.0] * horizon, False
    expanded, cyclic = _expand(
        _finite_nonnegative(prices, "electricity_prices"), horizon
    )
    return expanded, cyclic


class PowerDispatchOptimizer:
    """Build and solve one strict COPT rolling-horizon dispatch model."""

    _OBJECTIVES = {
        "min_cost", "min_carbon", "min_curtailment", "peak_shaving",
        "min_delay", "weighted", "custom",
    }

    def solve(self, problem: PowerDispatchProblem) -> PowerDispatchResult:
        if problem.horizon_hours <= 0 or problem.step_hours <= 0:
            raise ValueError("horizon_hours and step_hours must be positive")
        if problem.objective not in self._OBJECTIVES:
            raise ValueError(f"unknown power dispatch objective: {problem.objective}")
        requested_periods = max(1, int(math.ceil(float(problem.horizon_hours) / float(problem.step_hours))))
        horizon = max(len(problem.load_mw), requested_periods)
        load, cyclic = _expand(_finite_nonnegative(problem.load_mw, "load_mw"), horizon)
        if problem.fixed_generation_mw:
            fixed_generation, fixed_filled = _expand(
                _finite_nonnegative(problem.fixed_generation_mw, "fixed_generation_mw"),
                horizon,
            )
            cyclic = cyclic or fixed_filled
        else:
            fixed_generation = [0.0] * horizon
        cyclic = cyclic or problem.forecast_fill == "cyclic"
        price_factors, price_filled = electricity_price_factors(
            problem.electricity_prices, horizon
        )
        cyclic = cyclic or price_filled
        renewable_available: dict[str, list[float]] = {}
        for renewable in problem.renewables:
            values, filled = _expand(
                _finite_nonnegative(renewable.available_mw, f"renewable {renewable.id}"),
                horizon,
            )
            renewable_available[renewable.id] = values
            cyclic = cyclic or filled
        generator_reference: dict[str, list[float]] = {}
        for generator in problem.generators:
            if generator.reference_mw:
                values, filled = _expand(
                    _finite_nonnegative(
                        generator.reference_mw, f"generator reference {generator.id}"
                    ),
                    horizon,
                )
                generator_reference[generator.id] = values
                cyclic = cyclic or filled

        env = cp.Envr()
        model = env.createModel("rolling_power_dispatch")
        model.setParam(cp.COPT.Param.LogToConsole, 0)
        periods = range(horizon)

        generator_vars = {
            (generator.id, t): model.addVar(
                lb=float(generator.min_mw), ub=float(generator.max_mw),
                name=f"generator_{generator.id}_{t}",
            )
            for generator in problem.generators for t in periods
        }
        renewable_vars = {
            (renewable.id, t): model.addVar(
                lb=0.0, ub=renewable_available[renewable.id][t],
                name=f"renewable_{renewable.id}_{t}",
            )
            for renewable in problem.renewables for t in periods
        }
        charge_vars = {
            (storage.id, t): model.addVar(
                lb=0.0, ub=float(storage.max_power_mw), name=f"charge_{storage.id}_{t}"
            )
            for storage in problem.storages for t in periods
        }
        discharge_vars = {
            (storage.id, t): model.addVar(
                lb=0.0, ub=float(storage.max_power_mw), name=f"discharge_{storage.id}_{t}"
            )
            for storage in problem.storages for t in periods
        }
        storage_modes = {
            (storage.id, t): model.addVar(vtype=cp.COPT.BINARY, name=f"charging_{storage.id}_{t}")
            for storage in problem.storages for t in periods
        }
        soc_vars = {
            (storage.id, t): model.addVar(
                lb=float(storage.min_soc_mwh), ub=float(storage.max_soc_mwh),
                name=f"soc_{storage.id}_{t}",
            )
            for storage in problem.storages for t in range(horizon + 1)
        }
        grid_import = {
            t: model.addVar(
                lb=0.0, ub=float(problem.external_grid_max_import_mw),
                name=f"grid_import_{t}",
            ) for t in periods
        }
        grid_export = {
            t: model.addVar(
                lb=0.0, ub=float(problem.external_grid_max_export_mw),
                name=f"grid_export_{t}",
            ) for t in periods
        }
        reference_deviation = {
            (generator.id, t): model.addVar(
                lb=0.0, name=f"reference_deviation_{generator.id}_{t}"
            )
            for generator in problem.generators
            if generator.id in generator_reference
            for t in periods
        }

        for generator in problem.generators:
            previous = float(generator.initial_mw)
            for t in periods:
                current = generator_vars[generator.id, t]
                ramp_step = (
                    float(problem.control_interval_hours)
                    if t == 0 and problem.control_interval_hours is not None
                    else problem.step_hours
                )
                model.addConstr(
                    current - previous <= float(generator.ramp_up_mw_per_hour) * ramp_step
                )
                model.addConstr(
                    previous - current <= float(generator.ramp_down_mw_per_hour) * ramp_step
                )
                if generator.id in generator_reference:
                    reference = generator_reference[generator.id][t]
                    deviation = reference_deviation[generator.id, t]
                    model.addConstr(deviation >= current - reference)
                    model.addConstr(deviation >= reference - current)
                previous = current

        for storage in problem.storages:
            model.addConstr(soc_vars[storage.id, 0] == float(storage.initial_soc_mwh))
            for t in periods:
                charge = charge_vars[storage.id, t]
                discharge = discharge_vars[storage.id, t]
                mode = storage_modes[storage.id, t]
                model.addConstr(charge <= float(storage.max_power_mw) * mode)
                model.addConstr(discharge <= float(storage.max_power_mw) * (1 - mode))
                model.addConstr(
                    soc_vars[storage.id, t + 1]
                    == soc_vars[storage.id, t]
                    + charge * float(storage.charge_efficiency) * problem.step_hours
                    - discharge * problem.step_hours / float(storage.discharge_efficiency)
                )
            if storage.terminal_soc_mwh is not None:
                target = min(float(storage.max_soc_mwh), max(float(storage.min_soc_mwh), float(storage.terminal_soc_mwh)))
                model.addConstr(soc_vars[storage.id, horizon] >= target)
            # The SOC lower bound remains the operational reserve.  Do not
            # force a rolling horizon to end at its starting SOC: that would
            # keep an available battery idle while importing external power.

        net_demand_by_period: dict[int, object] = {}
        for t in periods:
            conventional = cp.quicksum(
                generator_vars[generator.id, t] for generator in problem.generators
            )
            renewable = cp.quicksum(
                renewable_vars[item.id, t] for item in problem.renewables
            )
            storage_supply = cp.quicksum(
                discharge_vars[item.id, t] - charge_vars[item.id, t]
                for item in problem.storages
            )
            model.addConstr(
                fixed_generation[t] + conventional + renewable + storage_supply
                + grid_import[t] - grid_export[t] == load[t]
            )
            # The peak-shaving target is the demand left for conventional
            # generation and the external grid after renewables and storage.
            # It must not be possible to hide a peak merely by swapping
            # conventional output for grid imports.
            net_demand_by_period[t] = (
                load[t] - fixed_generation[t] - renewable - storage_supply
            )

        peak = model.addVar(lb=0.0, name="conventional_peak")
        renewable_upper = sum(max(values) for values in renewable_available.values())
        storage_upper = sum(item.max_power_mw for item in problem.storages)
        valley = model.addVar(
            lb=-float(renewable_upper + storage_upper),
            name="conventional_valley",
        )
        for t in periods:
            model.addConstr(peak >= net_demand_by_period[t])
            model.addConstr(valley <= net_demand_by_period[t])

        cost_raw = cp.quicksum(
            (
                float(generator.cost_linear_yuan_per_mwh) * generator_vars[generator.id, t]
                + float(generator.cost_quadratic_yuan_per_mw2h)
                * generator_vars[generator.id, t] * generator_vars[generator.id, t]
            ) * problem.step_hours * price_factors[t]
            for generator in problem.generators for t in periods
        ) + cp.quicksum(
            float(storage.degradation_cost_per_mwh)
            * (charge_vars[storage.id, t] + discharge_vars[storage.id, t])
            * problem.step_hours
            for storage in problem.storages for t in periods
        ) + cp.quicksum(
            1000.0 * price_factors[t]
            * grid_import[t] * problem.step_hours
            for t in periods
        )
        carbon_raw = cp.quicksum(
            float(generator.emission_tco2_per_mwh)
            * generator_vars[generator.id, t] * problem.step_hours
            for generator in problem.generators for t in periods
        )
        curtailment_raw = cp.quicksum(
            (renewable_available[item.id][t] - renewable_vars[item.id, t])
            * problem.step_hours
            for item in problem.renewables for t in periods
        )
        peak_raw = peak - valley
        storage_raw = cp.quicksum(
            (charge_vars[item.id, t] + discharge_vars[item.id, t]) * problem.step_hours
            for item in problem.storages for t in periods
        )
        reference_raw = cp.quicksum(reference_deviation.values()) * problem.step_hours

        cost_reference = max(1.0, sum(
            (
                abs(item.cost_linear_yuan_per_mwh) * item.max_mw
                + abs(item.cost_quadratic_yuan_per_mw2h) * item.max_mw ** 2
            ) * horizon * problem.step_hours
            for item in problem.generators
        ))
        carbon_reference = max(1.0, sum(
            item.emission_tco2_per_mwh * item.max_mw * horizon * problem.step_hours
            for item in problem.generators
        ))
        curtailment_reference = max(1.0, sum(
            sum(values) * problem.step_hours for values in renewable_available.values()
        ))
        # Peak shaving acts on the variation around a large base load.  Using
        # the absolute system load here makes a realistic 10–30 MW peak on a
        # 6 GW grid numerically invisible beside the other normalized terms.
        peak_reference = max(1.0, max(load) - min(load))
        storage_reference = max(1.0, sum(
            item.max_power_mw * horizon * problem.step_hours for item in problem.storages
        ))
        dispatch_reference = max(1.0, sum(
            sum(values) * problem.step_hours
            for values in generator_reference.values()
        ))
        expressions = {
            "cost": cost_raw,
            "carbon": carbon_raw,
            "renewable_curtailment": curtailment_raw,
            "peak_shaving": peak_raw,
            "storage_degradation": storage_raw,
            "reference_deviation": reference_raw,
        }
        references = {
            "cost": cost_reference,
            "carbon": carbon_reference,
            "renewable_curtailment": curtailment_reference,
            "peak_shaving": peak_reference,
            "storage_degradation": storage_reference,
            "reference_deviation": dispatch_reference,
        }
        normalized = {name: expression / references[name] for name, expression in expressions.items()}

        if problem.objective == "min_cost":
            curtailment_weight = max(0.0, float((problem.objective_weights or {}).get("renewable_curtailment", 0.0)))
            objective_expression = normalized["cost"] + curtailment_weight * normalized["renewable_curtailment"] + 1e-8 * normalized["reference_deviation"]
        elif problem.objective == "min_carbon":
            objective_expression = normalized["carbon"] + 1e-8 * (
                normalized["cost"] + normalized["reference_deviation"]
            )
        elif problem.objective == "min_curtailment":
            objective_expression = normalized["renewable_curtailment"] + 1e-8 * (
                normalized["cost"] + normalized["reference_deviation"]
            )
        elif problem.objective == "peak_shaving":
            objective_expression = normalized["peak_shaving"] + 1e-8 * (
                normalized["cost"] + normalized["reference_deviation"]
            )
        elif problem.objective == "min_delay":
            # Delay is decided by the compute subproblem; cost is a deterministic
            # tie-breaker for its associated power subproblem.
            objective_expression = normalized["cost"]
        else:
            weights = problem.objective_weights or {"cost": 1.0}
            objective_expression = cp.quicksum(
                float(weights.get(name, 0.0)) * expression
                for name, expression in normalized.items()
            )
        model.setObjective(objective_expression, sense=cp.COPT.MINIMIZE)
        model.solve()

        if model.status != cp.COPT.OPTIMAL:
            infeasible = getattr(cp.COPT, "INFEASIBLE", object())
            status = "infeasible" if model.status == infeasible else str(model.status)
            return PowerDispatchResult(
                status=status,
                objective_value=None,
                generator_mw={},
                renewable_dispatched_mw={},
                renewable_curtailed_mw={},
                storage_power_mw={},
                storage_soc_mwh={},
                objective_components={},
                strictly_feasible=False,
                forecast_fill="cyclic" if cyclic else "native",
                external_grid_mw=[],
            )

        generator_output = {
            item.id: [float(generator_vars[item.id, t].x) for t in periods]
            for item in problem.generators
        }
        renewable_output = {
            item.id: [float(renewable_vars[item.id, t].x) for t in periods]
            for item in problem.renewables
        }
        storage_power = {
            item.id: [
                float(discharge_vars[item.id, t].x - charge_vars[item.id, t].x)
                for t in periods
            ]
            for item in problem.storages
        }
        storage_soc = {
            item.id: [float(soc_vars[item.id, t].x) for t in range(horizon + 1)]
            for item in problem.storages
        }
        raw_values = {name: float(expression.getValue()) for name, expression in expressions.items()}
        components = {
            name: {"raw": raw_values[name], "normalized": raw_values[name] / references[name]}
            for name in expressions
        }
        return PowerDispatchResult(
            status="optimal",
            objective_value=float(model.objval),
            generator_mw=generator_output,
            renewable_dispatched_mw=renewable_output,
            renewable_curtailed_mw={
                item.id: [
                    max(0.0, renewable_available[item.id][t] - renewable_output[item.id][t])
                    for t in periods
                ]
                for item in problem.renewables
            },
            storage_power_mw=storage_power,
            storage_soc_mwh=storage_soc,
            objective_components=components,
            strictly_feasible=True,
            forecast_fill="cyclic" if cyclic else "native",
            external_grid_mw=[
                float(grid_import[t].x - grid_export[t].x) for t in periods
            ],
        )

