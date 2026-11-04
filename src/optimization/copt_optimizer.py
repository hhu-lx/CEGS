from dataclasses import dataclass
from typing import Callable

import coptpy as cp

from src.domain.datacenter import DataCenter
from src.domain.task import Task
from src.domain.storage import EnergyStorage


@dataclass(frozen=True)
class OptimizationResult:
    status: str
    objective_value: float | None
    assignments: dict[str, str]


@dataclass(frozen=True)
class StorageDispatchResult:
    status: str
    objective_value: float | None
    charge_mw: list[float]
    discharge_mw: list[float]
    soc_mwh: list[float]


@dataclass(frozen=True)
class GlobalOptimizationResult:
    status: str
    objective_value: float | None
    assignments: dict[str, str]
    economic_cost: float
    carbon_emission: float


class CoptOptimizer:
    """Real COPT MILP for assigning ready tasks to feasible data centres."""

    def assign_tasks(
        self,
        tasks: list[Task],
        data_centers: list[DataCenter],
        *,
        objective: str = "min_cost",
        carbon_intensity: dict[int, float] | None = None,
        latency_ms: dict[tuple[str, str], float] | None = None,
        weights: dict[str, float] | None = None,
        energy_based: bool = False,
        objective_function: Callable | None = None,
        respect_allocated_data_center: bool = True,
        load_balance_weight: float = 0.0,
        minimum_active_center_tasks: int = 0,
    ) -> OptimizationResult:
        env = cp.Envr()
        model = env.createModel("task_assignment")
        variables: dict[tuple[str, str], object] = {}

        for task in tasks:
            preferred = task.user_specified_data_center or (
                task.allocated_data_center_id
                if respect_allocated_data_center else None
            )
            feasible = [
                dc for dc in data_centers
                if (not preferred or dc.id == preferred) and dc.can_allocate(task)
            ]
            if not feasible:
                return OptimizationResult("infeasible", None, {})
            for dc in feasible:
                variables[task.id, dc.id] = model.addVar(vtype=cp.COPT.BINARY, name=f"assign_{task.id}_{dc.id}")
            model.addConstr(cp.quicksum(variables[task.id, dc.id] for dc in feasible) == 1)

        assigned_compute_by_dc = {}
        for dc in data_centers:
            assigned_compute = cp.quicksum(
                task.required_compute * variables[task.id, dc.id]
                for task in tasks
                if (task.id, dc.id) in variables
            )
            assigned_compute_by_dc[dc.id] = assigned_compute
            model.addConstr(assigned_compute <= dc.available_compute)

            assigned_bandwidth = cp.quicksum(
                float(task.required_bandwidth_mbps or task.compute_bandwidth_requirement())
                * variables[task.id, dc.id]
                for task in tasks
                if (task.id, dc.id) in variables
            )
            model.addConstr(assigned_bandwidth <= dc.available_bandwidth)

            assigned_gpu = cp.quicksum(
                (task.required_gpu_count or 0) * variables[task.id, dc.id]
                for task in tasks
                if (task.id, dc.id) in variables
            )
            if any(task.required_gpu_count for task in tasks):
                compute_devices = [device for device in dc.device_pool if dc._is_compute_device(device)]
                if compute_devices:
                    gpu_capacity = sum(
                        max(0, device.quantity - dc.used_device_count(device.model))
                        for device in compute_devices
                    )
                    gpu_capacity = max(0, gpu_capacity - dc.used_device_count(dc._GENERIC_GPU_KEY))
                else:
                    gpu_capacity = max(0, int(dc.total_compute // dc._VIRTUAL_GPU_TFLOPS)
                                       - dc.used_device_count(dc._GENERIC_GPU_KEY))
                model.addConstr(assigned_gpu <= gpu_capacity)

        # When the batch is large enough, keep every center that has at
        # least one feasible task-placement option active.  Centers absent
        # from ``variables`` are deliberately exempt: they can be excluded
        # by a user placement, device type, network limit or resource limit.
        activity_floor = max(0, int(minimum_active_center_tasks or 0))
        eligible_centers = [
            dc for dc in data_centers
            if any((task.id, dc.id) in variables for task in tasks)
        ]
        if activity_floor and len(tasks) >= len(eligible_centers) * activity_floor:
            for dc in eligible_centers:
                model.addConstr(cp.quicksum(
                    variables[task.id, dc.id]
                    for task in tasks if (task.id, dc.id) in variables
                ) >= activity_floor)

        carbon_intensity = carbon_intensity or {}
        latency_ms = latency_ms or {}
        weights = weights or {"cost": 1.0, "carbon": 1.0, "delay": 1.0}

        def coefficient(task: Task, dc: DataCenter) -> float:
            if objective_function is not None:
                context = {
                    "objective": objective,
                    "carbon_intensity": carbon_intensity,
                    "latency_ms": latency_ms,
                    "weights": weights,
                    "energy_based": energy_based,
                }
                return float(objective_function(task, dc, context))
            if energy_based:
                # DataCenter power is MW and duration is hours; convert MWh
                # to kWh so it is compatible with yuan/kWh and kgCO2/kWh.
                energy_kwh = dc.power_for_task_mw(task) * task.duration_hours * 1000.0
                cost = energy_kwh * dc.current_price
                carbon = energy_kwh * carbon_intensity.get(dc.grid_bus_id, 0.5)
            else:
                cost = task.required_compute * dc.current_price
                carbon = task.required_compute * carbon_intensity.get(dc.grid_bus_id, 0.5)
            delay = latency_ms.get((task.region, dc.region), 20.0)
            if objective == "min_cost":
                return cost
            if objective == "min_carbon":
                return carbon
            if objective == "min_delay":
                return delay
            if objective == "weighted":
                return weights.get("cost", 0.0) * cost + weights.get("carbon", 0.0) * carbon + weights.get("delay", 0.0) * delay
            raise ValueError(f"unknown optimization objective: {objective}")

        # Keep the economic/environmental objective primary, while adding a
        # soft utilization penalty.  The penalty is scaled to the objective
        # coefficients so it remains meaningful for both yuan/MWh and custom
        # objective functions, without making a feasible placement impossible.
        coefficients = {
            (task.id, dc.id): coefficient(task, dc)
            for task in tasks for dc in data_centers
            if (task.id, dc.id) in variables
        }
        positive_coefficients = [abs(value) for value in coefficients.values() if abs(value) > 1e-9]
        balance_reference = sum(positive_coefficients) / len(positive_coefficients) if positive_coefficients else 1.0
        balance_weight = max(0.0, float(load_balance_weight or 0.0))
        objective_terms = []
        for task in tasks:
            for dc in data_centers:
                key = (task.id, dc.id)
                if key not in variables:
                    continue
                objective_terms.append(
                    coefficients[key] * variables[key]
                )
        balance_range = 0.0
        if balance_weight > 0 and len(data_centers) > 1:
            balance_peak = model.addVar(lb=0.0, ub=1.0, name="balance_peak")
            balance_floor = model.addVar(lb=0.0, ub=1.0, name="balance_floor")
            for dc in data_centers:
                utilization = (
                    float(dc.used_compute) + assigned_compute_by_dc[dc.id]
                ) / float(dc.total_compute)
                model.addConstr(balance_peak >= utilization)
                model.addConstr(balance_floor <= utilization)
            balance_range = balance_peak - balance_floor
        model.setObjective(
            cp.quicksum(objective_terms) + balance_weight * balance_reference * balance_range,
            sense=cp.COPT.MINIMIZE,
        )
        model.solve()
        if model.status != cp.COPT.OPTIMAL:
            # The activity floor is a balancing preference.  A restrictive
            # floor must not make an otherwise feasible task batch wait
            # forever when only a subset of centers can satisfy its resource
            # requirements.  Retry once without that soft preference.
            if activity_floor > 0:
                return self.assign_tasks(
                    tasks,
                    data_centers,
                    objective=objective,
                    carbon_intensity=carbon_intensity,
                    latency_ms=latency_ms,
                    weights=weights,
                    energy_based=energy_based,
                    objective_function=objective_function,
                    respect_allocated_data_center=respect_allocated_data_center,
                    load_balance_weight=load_balance_weight,
                    minimum_active_center_tasks=0,
                )
            infeasible_status = getattr(cp.COPT, "INFEASIBLE", object())
            status = "infeasible" if model.status == infeasible_status else str(model.status)
            return OptimizationResult(status, None, {})

        assignments = {
            task_id: dc_id
            for (task_id, dc_id), variable in variables.items()
            if variable.x > 0.5
        }
        return OptimizationResult("optimal", float(model.objval), assignments)

    def optimize_storage(self, storage: EnergyStorage, prices: list[float], step_hours: float) -> StorageDispatchResult:
        """Solve a time-indexed storage arbitrage MILP with explicit SOC balance."""
        if not prices or step_hours <= 0:
            raise ValueError("prices and a positive step_hours are required")
        env = cp.Envr()
        model = env.createModel("storage_dispatch")
        periods = range(len(prices))
        charge = [model.addVar(lb=0, ub=storage.max_power_mw, name=f"charge_{t}") for t in periods]
        discharge = [model.addVar(lb=0, ub=storage.max_power_mw, name=f"discharge_{t}") for t in periods]
        mode = [model.addVar(vtype=cp.COPT.BINARY, name=f"mode_{t}") for t in periods]
        soc = [model.addVar(lb=storage.min_soc_mwh, ub=storage.max_soc_mwh, name=f"soc_{t}") for t in range(len(prices) + 1)]
        model.addConstr(soc[0] == storage.soc_mwh)
        for t in periods:
            model.addConstr(charge[t] <= storage.max_power_mw * mode[t])
            model.addConstr(discharge[t] <= storage.max_power_mw * (1 - mode[t]))
            model.addConstr(soc[t + 1] == soc[t] + charge[t] * storage.charge_efficiency * step_hours - discharge[t] * step_hours / storage.discharge_efficiency)
        model.setObjective(cp.quicksum(
            prices[t] * (charge[t] - discharge[t]) * step_hours + storage.degradation_cost_per_mwh * (charge[t] + discharge[t]) * step_hours
            for t in periods
        ), sense=cp.COPT.MINIMIZE)
        model.solve()
        if model.status != cp.COPT.OPTIMAL:
            return StorageDispatchResult(str(model.status), None, [], [], [])
        return StorageDispatchResult(
            "optimal", float(model.objval),
            [float(item.x) for item in charge], [float(item.x) for item in discharge], [float(item.x) for item in soc],
        )

    def optimize_storage_realtime(
        self,
        storage: EnergyStorage,
        *,
        net_load_mw: float,
        reference_load_mw: float,
        electricity_price: float,
        step_hours: float,
        weights: dict[str, float] | None = None,
        renewable_surplus_mw: float = 0.0,
    ) -> dict:
        """Choose one feasible storage action by minimizing live net-load deviation."""
        if step_hours <= 0:
            raise ValueError("step_hours must be positive")
        weights = weights or {}
        env = cp.Envr()
        model = env.createModel("realtime_storage_dispatch")
        model.setParam(cp.COPT.Param.LogToConsole, 0)
        charge = model.addVar(lb=0.0, ub=storage.max_power_mw, name="charge")
        discharge = model.addVar(lb=0.0, ub=storage.max_power_mw, name="discharge")
        charging = model.addVar(vtype=cp.COPT.BINARY, name="charging")
        next_soc = model.addVar(lb=storage.min_soc_mwh, ub=storage.max_soc_mwh, name="next_soc")
        positive_deviation = model.addVar(lb=0.0, name="positive_deviation")
        negative_deviation = model.addVar(lb=0.0, name="negative_deviation")
        renewable_absorption = model.addVar(
            lb=0.0,
            ub=max(0.0, float(renewable_surplus_mw)),
            name="renewable_absorption",
        )
        model.addConstr(charge <= storage.max_power_mw * charging)
        model.addConstr(discharge <= storage.max_power_mw * (1 - charging))
        model.addConstr(
            next_soc == storage.soc_mwh
            + charge * storage.charge_efficiency * step_hours
            - discharge * step_hours / storage.discharge_efficiency
        )
        net_after = float(net_load_mw) + charge - discharge
        model.addConstr(
            net_after - float(reference_load_mw)
            == positive_deviation - negative_deviation
        )
        model.addConstr(renewable_absorption <= charge)
        peak_weight = float(weights.get("peak_shaving", 1.0))
        cost_weight = float(weights.get("cost", 0.0))
        degradation_weight = float(weights.get("storage_degradation", 0.0))
        curtailment_weight = float(weights.get("renewable_curtailment", 0.0))
        model.setObjective(
            peak_weight * (positive_deviation + negative_deviation)
            + cost_weight * float(electricity_price) * (charge - discharge) * step_hours
            + degradation_weight * float(storage.degradation_cost_per_mwh) * (charge + discharge) * step_hours
            - curtailment_weight * renewable_absorption * step_hours,
            sense=cp.COPT.MINIMIZE,
        )
        model.solve()
        if model.status != cp.COPT.OPTIMAL:
            return {"status": "infeasible", "objective_value": None, "power_mw": 0.0}
        power = float(discharge.x - charge.x)
        return {
            "status": "optimal",
            "objective_value": float(model.objval),
            "power_mw": power,
            "charge_mw": float(charge.x),
            "discharge_mw": float(discharge.x),
            "soc_mwh": float(next_soc.x),
            "net_load_after_storage_mw": float(net_load_mw) - power,
        }

    def optimize_renewable_dispatch(
        self,
        available_mw: dict[str, float],
        *,
        linear_constraints: list[dict] | None = None,
    ) -> dict:
        """Maximize renewable use subject to linearized grid operating limits."""
        env = cp.Envr()
        model = env.createModel("renewable_dispatch")
        model.setParam(cp.COPT.Param.LogToConsole, 0)
        variables = {
            source: model.addVar(lb=0.0, ub=max(0.0, float(power)), name=f"renewable_{source}")
            for source, power in available_mw.items()
        }
        for index, constraint in enumerate(linear_constraints or []):
            coefficients = constraint.get("coefficients", {})
            lhs = cp.quicksum(
                float(coefficients.get(source, 0.0)) * variable
                for source, variable in variables.items()
            )
            model.addConstr(lhs <= float(constraint["rhs"]), name=f"grid_limit_{index}")
        # Maximizing dispatched renewable generation is equivalent to
        # minimizing total curtailment because availability is fixed.
        model.setObjective(-cp.quicksum(variables.values()), sense=cp.COPT.MINIMIZE)
        model.solve()
        if model.status != cp.COPT.OPTIMAL:
            return {"status": "infeasible", "dispatched_mw": {}, "curtailed_mw": {}}
        dispatched = {source: float(variable.x) for source, variable in variables.items()}
        available = {source: max(0.0, float(value)) for source, value in available_mw.items()}
        return {
            "status": "optimal",
            "objective_value": float(model.objval),
            "dispatched_mw": dispatched,
            "curtailed_mw": {source: max(0.0, available[source] - dispatched[source]) for source in available},
        }

    def global_optimize(self, tasks, data_centers, *, objective="weighted", carbon_intensity=None, weights=None, objective_function=None) -> GlobalOptimizationResult:
        """Global assignment mode: one COPT model selects placement while pricing both cost and carbon."""
        carbon_intensity = carbon_intensity or {}
        result = self.assign_tasks(
            tasks, data_centers, objective=objective, carbon_intensity=carbon_intensity,
            weights=weights or {"cost": 1.0, "carbon": 1.0, "delay": 0.0},
            energy_based=True,
            objective_function=objective_function,
        )
        centers = {center.id: center for center in data_centers}
        tasks_by_id = {task.id: task for task in tasks}
        economic_cost = sum(
            centers[dc_id].power_for_task_mw(tasks_by_id[task_id])
            * tasks_by_id[task_id].duration_hours * 1000.0
            * centers[dc_id].current_price
            for task_id, dc_id in result.assignments.items()
        )
        carbon_emission = sum(
            centers[dc_id].power_for_task_mw(tasks_by_id[task_id])
            * tasks_by_id[task_id].duration_hours * 1000.0
            * carbon_intensity.get(centers[dc_id].grid_bus_id, 0.5)
            for task_id, dc_id in result.assignments.items()
        )
        return GlobalOptimizationResult(result.status, result.objective_value, result.assignments, economic_cost, carbon_emission)
