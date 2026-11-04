# Rolling Storage MPC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the default electrical dispatch use a fine-grained rolling forecast, renewable-curtailment-aware storage scheduling, and a terminal SOC guard.

**Architecture:** Reuse the existing `PowerDispatchOptimizer` horizon model. The engine will build the horizon using `forecast_horizon_hours` and `forecast_step_minutes`, execute only period 0, and re-solve each renewable optimization interval. The model will optionally enforce a per-storage terminal SOC target and include configured curtailment weight in `min_cost`.

**Tech Stack:** Python, COPT MILP, pytest.

**Spec:** `docs/superpowers/specs/2026-11-01-generation-net-load-design.md`

## Global Constraints

- Rolling control executes only the first period of each solved horizon.
- Existing storage/grid balance and SOC limits remain hard constraints.
- Existing callers that do not request a terminal SOC target remain behavior-compatible.

## Review Focus

- Fine step sizes must produce the expected number of horizon periods.
- Terminal SOC targets must never exceed storage capacity or make feasible problems infeasible unexpectedly.
- Curtailment weighting must not change ordinary no-surplus min-cost dispatch.
- Existing storage-before-grid behavior must remain true.

### Task 1: Model-level rolling horizon controls

**Files:** `src/optimization/power_dispatch.py`, `tests/optimization/test_power_dispatch.py`

- [ ] Add failing tests for terminal SOC and curtailment-aware min-cost charging.
- [ ] Add optional `terminal_soc_mwh` to storage inputs and constrain final SOC when set.
- [ ] Include configured renewable-curtailment weight in `min_cost` objective.
- [ ] Run focused optimizer tests.

### Task 2: Engine fine-grained rolling integration

**Files:** `src/simulation/engine.py`, `src/infrastructure/pandapower_adapter.py`, `tests/simulation/test_engine_optimization.py`

- [ ] Add failing test that the heuristic problem uses configured forecast horizon and step minutes.
- [ ] Pass `forecast_horizon_hours` and `forecast_step_minutes` into heuristic problem construction.
- [ ] Make price forecast length use actual period count, not integer hours.
- [ ] Set terminal SOC targets to current SOC for rolling windows.
- [ ] Run focused engine tests.

### Task 3: Verification

- [ ] Run optimizer, engine, storage, and report tests.
- [ ] Run the full suite and report unrelated pre-existing failures separately.

