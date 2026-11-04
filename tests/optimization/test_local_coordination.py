from dataclasses import dataclass

from src.optimization.local_coordination import LocalCoordinationOptimizer
from src.optimization.power_dispatch import PowerDispatchResult


@dataclass
class AssignmentResult:
    status: str
    objective_value: float | None
    assignments: dict[str, str]


def power_result(value: float, *, feasible: bool = True) -> PowerDispatchResult:
    return PowerDispatchResult(
        status="optimal" if feasible else "infeasible",
        objective_value=value if feasible else None,
        generator_mw={"g": [10.0]} if feasible else {},
        renewable_dispatched_mw={}, renewable_curtailed_mw={},
        storage_power_mw={}, storage_soc_mwh={}, objective_components={},
        strictly_feasible=feasible, forecast_fill="native",
    )


class SequenceTaskSolver:
    def __init__(self, assignments, events):
        self.assignments = list(assignments)
        self.events = events
        self.calls = 0

    def solve(self, tasks, data_centers, context):
        self.events.append(("task", self.calls + 1, dict(context.get("power_feedback", {}))))
        value = self.assignments[min(self.calls, len(self.assignments) - 1)]
        self.calls += 1
        return AssignmentResult("optimal", float(self.calls), value)


class SequencePowerSolver:
    def __init__(self, results, events):
        self.results = list(results)
        self.events = events
        self.calls = 0

    def solve(self, problem):
        self.events.append(("power", self.calls + 1, problem))
        value = self.results[min(self.calls, len(self.results) - 1)]
        self.calls += 1
        return value


def test_local_coordination_feedback_order_and_identical_assignment_convergence():
    events = []
    task_solver = SequenceTaskSolver([{"t": "a"}, {"t": "a"}, {"t": "a"}], events)
    power_solver = SequencePowerSolver([power_result(10), power_result(9), power_result(8)], events)

    result = LocalCoordinationOptimizer(task_solver, power_solver).solve(
        tasks=["t"], data_centers=["a"], task_context={},
        power_problem_factory=lambda assignments, iteration, context: (assignments, iteration),
        max_iterations=5, tolerance=1e-3,
    )

    assert result.converged is True
    assert result.iterations == 2
    assert result.assignments == {"t": "a"}
    assert [event[0] for event in events] == ["task", "power", "task", "power"]
    assert events[2][2]["objective_value"] == 11.0


def test_local_coordination_stops_on_relative_objective_tolerance():
    events = []
    task_solver = SequenceTaskSolver([{"t": "a"}, {"t": "b"}, {"t": "a"}], events)
    power_solver = SequencePowerSolver([power_result(100.0), power_result(99.00005)], events)

    result = LocalCoordinationOptimizer(task_solver, power_solver).solve(
        tasks=["t"], data_centers=["a", "b"], task_context={},
        power_problem_factory=lambda *args: args[0], max_iterations=5, tolerance=1e-3,
    )

    assert result.converged is True
    assert result.iterations == 2
    assert len(result.objective_history) == 2


def test_local_coordination_never_exceeds_five_iterations():
    events = []
    alternating = [{"t": "a"}, {"t": "b"}] * 4
    task_solver = SequenceTaskSolver(alternating, events)
    power_solver = SequencePowerSolver([power_result(100 - i * 10) for i in range(5)], events)

    result = LocalCoordinationOptimizer(task_solver, power_solver).solve(
        tasks=["t"], data_centers=["a", "b"], task_context={},
        power_problem_factory=lambda *args: args[0], max_iterations=9, tolerance=1e-9,
    )

    assert result.iterations == 5
    assert result.converged is False


def test_local_coordination_preserves_previous_strict_feasible_iteration():
    events = []
    task_solver = SequenceTaskSolver([{"t": "a"}, {"t": "b"}, {"t": "a"}], events)
    second = power_result(8.0)
    power_solver = SequencePowerSolver([power_result(10.0), second, power_result(0, feasible=False)], events)

    result = LocalCoordinationOptimizer(task_solver, power_solver).solve(
        tasks=["t"], data_centers=["a", "b"], task_context={},
        power_problem_factory=lambda *args: args[0], max_iterations=5, tolerance=1e-9,
    )

    assert result.status == "fallback_feasible"
    assert result.assignments == {"t": "b"}
    assert result.power_dispatch is second
    assert result.iterations == 3


def test_local_coordination_first_iteration_infeasible_keeps_tasks_queued():
    events = []
    result = LocalCoordinationOptimizer(
        SequenceTaskSolver([{"t": "a"}], events),
        SequencePowerSolver([power_result(0, feasible=False)], events),
    ).solve(
        tasks=["t"], data_centers=["a"], task_context={},
        power_problem_factory=lambda *args: args[0],
    )

    assert result.status == "infeasible"
    assert result.assignments == {}
    assert result.power_dispatch is None
    assert result.converged is False

