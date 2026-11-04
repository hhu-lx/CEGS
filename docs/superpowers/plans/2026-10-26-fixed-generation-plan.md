# Fixed Generation Plan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the 24-hour conventional generation plan cover about 80% of load with variation, while renewable surplus is curtailed rather than silently reducing that plan.

**Architecture:** Generate a new per-unit base-generation trace from the existing load trace and configured capacities. Treat that trace as a fixed supply in the adapter and both optimization models; renewable dispatch remains a decision variable limited by residual load.

**Tech Stack:** Python, Pandapower, COPT, pytest, CSV time series.

**Spec:** `docs/superpowers/specs/2026-10-26-fixed-generation-plan-design.md`

## Global Constraints

- Preserve the existing 24-hour, 86400-point input data cadence.
- Use user-supplied load, wind, PV and base-generation data; do not activate topology default load/generation.
- Do not change wind/PV capacities, external-grid capacity or task configuration.

## Review Focus

- Plan coverage must be measured against the actual configured load capacity, not an obsolete nominal base.
- A green surplus over the residual load must become curtailment, not negative grid exchange.
- A renewable shortage must retain the entire fixed conventional injection before external import.
- Empty or shorter fixed-generation forecasts must retain the optimizer's established cyclic forecast behavior.
- The global joint model must have the same fixed-injection balance as the local optimizer.

---

### Task 1: Generate and validate the 80% conventional plan

**Files:**
- Modify: `config/base_generation_pu_second.csv`
- Test: `tests/infrastructure/test_storage_injection.py`

**Interfaces:**
- Consumes: configured load time series and `grid.load_capacity_mw` / `grid.base_generation_capacity_mw`.
- Produces: a 86400-point per-unit conventional-generation trace.

- [ ] **Step 1: Write the failing coverage test**

Assert that the loaded base-generation trace divided by actual MW load has a mean near 0.80 and a non-zero range.

- [ ] **Step 2: Run the coverage test to verify it fails**

Run: `F:\python\python.exe -m pytest tests/infrastructure/test_storage_injection.py -q`
Expected: FAIL because the current trace averages about 1.87 of actual load.

- [ ] **Step 3: Regenerate `base_generation_pu_second.csv`**

Write one per-unit value per second using the actual load MW multiplied by a smooth 0.80-centred bounded perturbation, then divide by `base_generation_capacity_mw=7200`.

- [ ] **Step 4: Run the coverage test to verify it passes**

Run: `F:\python\python.exe -m pytest tests/infrastructure/test_storage_injection.py -q`
Expected: PASS.

### Task 2: Preserve the plan as a fixed injection

**Files:**
- Modify: `src/infrastructure/pandapower_adapter.py`
- Modify: `src/optimization/power_dispatch.py`
- Modify: `src/optimization/joint_coordination.py`
- Test: `tests/infrastructure/test_storage_injection.py`
- Test: `tests/optimization/test_power_dispatch.py`
- Test: `tests/optimization/test_joint_coordination.py`

**Interfaces:**
- Consumes: `PowerDispatchProblem.fixed_generation_mw: list[float]`.
- Produces: power balances where fixed generation is always included and wind/PV are curtailed above residual demand.

- [ ] **Step 1: Write failing residual-load tests**

For load 100 MW, fixed generation 80 MW and wind 30 MW, assert 20 MW wind dispatch, 10 MW curtailment and zero grid import in the local and joint models.

- [ ] **Step 2: Run those tests to verify they fail**

Run: `F:\python\python.exe -m pytest tests/optimization/test_power_dispatch.py tests/optimization/test_joint_coordination.py -q`
Expected: FAIL because the present adapter reduces the fixed plan after renewable availability.

- [ ] **Step 3: Keep fixed generation independent of renewable dispatch**

In the adapter, create the dispatch problem with the scheduled base value and do not reduce it when wind/PV is dispatched. In both COPT models, include the same fixed series in balance and net-demand expressions.

- [ ] **Step 4: Run focused tests to verify they pass**

Run: `F:\python\python.exe -m pytest tests/infrastructure/test_storage_injection.py tests/optimization/test_power_dispatch.py tests/optimization/test_joint_coordination.py -q --disable-warnings`
Expected: PASS.

### Task 3: Verify end-to-end modes

**Files:**
- Test: existing simulation and API tests.

**Interfaces:**
- Consumes: generated time series and fixed-injection dispatch problem.
- Produces: feasible heuristic, local and global operation with renewable curtailment when surplus occurs.

- [ ] **Step 1: Reproduce the five-bus global configuration**

Run a `SimulationEngine` with `config/examples/custom_topology_test.json`, global weighted optimization and its real 24-hour horizon.

- [ ] **Step 2: Confirm feasible global AC dispatch**

Assert `status == "optimal"` and `strictly_feasible is True`.

- [ ] **Step 3: Run the full test suite**

Run: `F:\python\python.exe -m pytest -q --disable-warnings`
Expected: report all tests passing, or identify unrelated existing failures explicitly.
