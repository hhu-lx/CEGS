# Minimum Data Center Activity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure every feasible data center receives work when a task batch is large enough, without overriding safety, resource, or user-placement constraints.

**Architecture:** Add one `minimum_active_center_tasks` setting to the optimization configuration. Both the local assignment model and the global joint model derive an eligible-center set from their existing placement variables, then require at least the configured number of assignments for each eligible center only when the batch can cover all eligible centers.

**Tech Stack:** Python, Pydantic, COPT MILP/MIQP, pytest.

**Spec:** `docs/superpowers/specs/2026-10-25-minimum-datacenter-activity-design.md`

## Global Constraints

- Do not override a user-specified data center.
- Do not make an infeasible resource, bandwidth, GPU, or AC-power-flow plan feasible by force.
- Do not force distribution when the ready batch has fewer tasks than eligible centers.
- Preserve the existing soft utilization-range objective.

## Review Focus

- User-fixed placement remains fixed even when the batch contains enough tasks; Task 2 test covers this.
- A center with no valid task-placement variable is exempt; Task 2 test covers this.
- Fewer tasks than eligible centers remains feasible and unconstrained; Task 1 test covers this.
- Expanding the global model does not include future-start tasks as current-period activity; Task 2 test covers this.
- Default configuration applies equally to local and global modes; Task 3 configuration test covers this.

---

### Task 1: Local assignment activity floor

**Files:**
- Modify: `src/optimization/copt_optimizer.py:39-180`
- Modify: `tests/optimization/test_copt_optimizer.py`

**Interfaces:**
- Consumes: `CoptOptimizer.assign_tasks(..., minimum_active_center_tasks: int = 0)`.
- Produces: local MILP assignments in which each eligible center receives the requested minimum number of tasks when the batch is large enough.

- [ ] **Step 1: Write failing tests**

```python
def test_copt_activity_floor_uses_every_eligible_center_despite_cost_preference():
    result = CoptOptimizer().assign_tasks(tasks, centers, minimum_active_center_tasks=1)
    assert set(result.assignments.values()) == {"a", "b", "c"}

def test_copt_activity_floor_is_not_applied_when_batch_is_smaller_than_eligible_centers():
    result = CoptOptimizer().assign_tasks(tasks, centers, minimum_active_center_tasks=1)
    assert result.status == "optimal"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `F:\python\python.exe -m pytest -q tests/optimization/test_copt_optimizer.py -k activity_floor`

Expected: FAIL because `assign_tasks` does not accept `minimum_active_center_tasks`.

- [ ] **Step 3: Implement the local constraint**

Extend `CoptOptimizer.assign_tasks` with `minimum_active_center_tasks: int = 0`. When `len(tasks) >= eligible_center_count * minimum_active_center_tasks`, add `sum(assignments_to_center) >= minimum_active_center_tasks` for every center with at least one assignment variable.

- [ ] **Step 4: Run local optimizer tests**

Run: `F:\python\python.exe -m pytest -q tests/optimization/test_copt_optimizer.py`

Expected: PASS.

### Task 2: Global joint-model activity floor

**Files:**
- Modify: `src/optimization/joint_coordination.py:110-180`
- Modify: `tests/optimization/test_joint_coordination.py`

**Interfaces:**
- Consumes: `JointCoordinationOptimizer.solve(..., minimum_active_center_tasks: int = 0)`.
- Produces: global placement with one immediate-start task per eligible center when enough ready tasks exist.

- [ ] **Step 1: Write failing tests**

```python
def test_joint_activity_floor_uses_every_eligible_center_despite_cost_preference():
    result = JointCoordinationOptimizer().solve(tasks, centers, problem, minimum_active_center_tasks=1, ...)
    assert set(result.assignments.values()) == {"a", "b", "c"}

def test_joint_activity_floor_exempts_user_fixed_or_ineligible_center():
    result = JointCoordinationOptimizer().solve(tasks, centers, problem, minimum_active_center_tasks=1, ...)
    assert result.status == "optimal"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `F:\python\python.exe -m pytest -q tests/optimization/test_joint_coordination.py -k activity_floor`

Expected: FAIL because `solve` does not accept `minimum_active_center_tasks`.

- [ ] **Step 3: Implement the global constraint**

Extend `JointCoordinationOptimizer.solve` and `_solve_model` with `minimum_active_center_tasks: int = 0`. Derive eligible centers from immediate-start placement variables and add a minimum count only when enough immediate-start tasks exist to satisfy every eligible center.

- [ ] **Step 4: Run global optimizer tests**

Run: `F:\python\python.exe -m pytest -q tests/optimization/test_joint_coordination.py`

Expected: PASS.

### Task 3: Runtime configuration and regression coverage

**Files:**
- Modify: `src/config/models.py:80-105`
- Modify: `config/platform.yaml`
- Modify: `config/platform.example.yaml`
- Modify: `src/simulation/engine.py:975-1000,1133-1155`
- Modify: `tests/config/test_platform_config.py`
- Modify: `tests/simulation/test_engine_optimization.py`

**Interfaces:**
- Consumes: `optimization.minimum_active_center_tasks`.
- Produces: the same activity floor in hierarchical/local and joint/global runtime paths.

- [ ] **Step 1: Write failing configuration and forwarding tests**

```python
assert config.optimization.minimum_active_center_tasks == 1
assert captured_kwargs["minimum_active_center_tasks"] == 1
```

- [ ] **Step 2: Run tests to verify failure**

Run: `F:\python\python.exe -m pytest -q tests/config/test_platform_config.py tests/simulation/test_engine_optimization.py -k minimum_active_center_tasks`

Expected: FAIL because the setting is absent or not forwarded.

- [ ] **Step 3: Add setting and forward it**

Add `minimum_active_center_tasks: int = Field(default=1, ge=0)` to `OptimizationConfig`, document it in both YAML files, and forward it from both engine optimization paths.

- [ ] **Step 4: Run targeted regression suite**

Run: `F:\python\python.exe -m pytest -q tests/config tests/optimization/test_copt_optimizer.py tests/optimization/test_joint_coordination.py tests/simulation/test_engine_optimization.py --disable-warnings`

Expected: PASS.
