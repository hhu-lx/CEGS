"""Alternating compute/power coordination for the local optimization mode."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from src.optimization.power_dispatch import PowerDispatchOptimizer, PowerDispatchResult


@dataclass(frozen=True)
class LocalCoordinationResult:
    status: str
    assignments: dict[str, str]
    power_dispatch: PowerDispatchResult | None
    iterations: int
    converged: bool
    objective_history: list[float]


def _field(value: Any, name: str, default=None):
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


class LocalCoordinationOptimizer:
    """Alternate task placement and strict power dispatch for at most five rounds."""

    def __init__(self, task_solver, power_solver=None):
        self.task_solver = task_solver
        self.power_solver = power_solver or PowerDispatchOptimizer()

    def solve(
        self,
        tasks,
        data_centers,
        task_context: dict,
        power_problem_factory: Callable,
        *,
        max_iterations: int = 5,
        tolerance: float = 1e-3,
    ) -> LocalCoordinationResult:
        limit = max(1, min(5, int(max_iterations)))
        context = dict(task_context or {})
        objective_history: list[float] = []
        previous_assignments: dict[str, str] | None = None
        last_feasible: tuple[dict[str, str], PowerDispatchResult] | None = None

        for iteration in range(1, limit + 1):
            assignment_result = self.task_solver.solve(tasks, data_centers, context)
            assignments = dict(_field(assignment_result, "assignments", {}) or {})
            assignment_status = str(_field(assignment_result, "status", "infeasible"))
            if assignment_status not in {"optimal", "optimal_solution"}:
                return self._fallback(last_feasible, iteration, objective_history)

            problem = power_problem_factory(assignments, iteration, context)
            power_dispatch = self.power_solver.solve(problem)
            if not power_dispatch.strictly_feasible:
                return self._fallback(last_feasible, iteration, objective_history)

            validator = context.get("validate_power_dispatch")
            if validator is not None:
                validation = validator(power_dispatch, assignments, iteration)
                feasible = validation.get("feasible", False) if isinstance(validation, dict) else bool(validation)
                if not feasible:
                    return self._fallback(last_feasible, iteration, objective_history)

            task_objective = float(_field(assignment_result, "objective_value", 0.0) or 0.0)
            power_objective = float(power_dispatch.objective_value or 0.0)
            combined_objective = task_objective + power_objective
            objective_history.append(combined_objective)
            last_feasible = (assignments, power_dispatch)

            assignments_stable = previous_assignments is not None and assignments == previous_assignments
            objective_stable = False
            if len(objective_history) >= 2:
                previous = objective_history[-2]
                objective_stable = (
                    abs(combined_objective - previous) / max(1.0, abs(previous))
                    <= float(tolerance)
                )
            feedback_builder = context.get("build_power_feedback")
            context["power_feedback"] = (
                feedback_builder(power_dispatch, assignments, iteration)
                if feedback_builder is not None
                else {
                    "objective_value": combined_objective,
                    "objective_components": power_dispatch.objective_components,
                }
            )
            if assignments_stable or objective_stable:
                return LocalCoordinationResult(
                    status="optimal",
                    assignments=assignments,
                    power_dispatch=power_dispatch,
                    iterations=iteration,
                    converged=True,
                    objective_history=objective_history,
                )
            previous_assignments = assignments

        assert last_feasible is not None
        return LocalCoordinationResult(
            status="optimal",
            assignments=last_feasible[0],
            power_dispatch=last_feasible[1],
            iterations=limit,
            converged=False,
            objective_history=objective_history,
        )

    @staticmethod
    def _fallback(last_feasible, iterations, objective_history) -> LocalCoordinationResult:
        if last_feasible is None:
            return LocalCoordinationResult(
                status="infeasible", assignments={}, power_dispatch=None,
                iterations=iterations, converged=False,
                objective_history=list(objective_history),
            )
        return LocalCoordinationResult(
            status="fallback_feasible",
            assignments=last_feasible[0],
            power_dispatch=last_feasible[1],
            iterations=iterations,
            converged=False,
            objective_history=list(objective_history),
        )

