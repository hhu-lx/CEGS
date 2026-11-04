# Conservative Simulation Speedup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reduce duplicate optimization preparation and validated-result work in all three modes while preserving point-by-point outputs.

**Architecture:** Add a bounded, versioned cache owned by `SimulationEngine`. Cache entries are keyed by mode, simulation state version, task batch fingerprint, and relevant configuration; only strictly feasible immutable results are copied back to runtime state. Keep all existing solver calls, AC validation, fallback behavior, and scheduling intervals unchanged on cache misses.

**Tech Stack:** Python, dataclasses/copy, pytest, existing COPT and pandapower adapters.

**Spec:** `docs/superpowers/specs/2026-11-04-conservative-simulation-speedup-design.md`

## Global Constraints

- Task allocation, controls, AC feasibility, and report samples must remain point-by-point identical.
- Do not change step size, optimization intervals, horizons, MIP limits, solver objectives, or validation frequency.
- Cache only strictly feasible results and return defensive copies.
- Any task, grid, renewable, storage, or configuration state change invalidates affected entries.

## Review Focus

- A task batch with the same IDs but changed allocation/resource state must miss the cache.
- A renewable or load change at the same simulation second must invalidate electrical results.
- An AC-infeasible result must never be cached or reused.
- Mutable nested dispatch results must not be shared between cache and live engine state.
- Cache size must remain bounded during a long simulation.

### Task 1: Add versioned cache primitives

**Files:**
- Modify: `src/simulation/engine.py` (engine initialization and helper methods)
- Test: `tests/simulation/test_engine_optimization.py`

**Interfaces:**
- Add `_bump_state_version(reason: str) -> None`.
- Add `_optimization_cache_get(key: tuple) -> dict | None` and `_optimization_cache_put(key: tuple, value: dict) -> None`.
- Add `_optimization_cache_key(mode: str, tasks: list[Task]) -> tuple` using task identity/timing/resource fields plus engine state/config version.

- [ ] Write tests for hit/miss, invalidation, defensive copy, and bounded eviction.
- [ ] Run the focused tests and confirm they fail before implementation.
- [ ] Implement an `OrderedDict` cache with a fixed maximum size and deep copies on read/write.
- [ ] Add state-version bumps at existing task/grid/storage/config mutation boundaries without changing scheduling behavior.
- [ ] Run the focused tests and confirm they pass.

### Task 2: Cache heuristic and local optimization preparation/results

**Files:**
- Modify: `src/simulation/engine.py` (`_run_heuristic_cycle`, `_run_local_coordination`)
- Test: `tests/simulation/test_engine_optimization.py`, `tests/simulation/test_engine_step.py`

**Interfaces:**
- Reuse Task 1 cache helpers.

- [ ] Add instrumentation tests showing repeated identical heuristic/local calls reuse the validated result and do not call the underlying solve path again.
- [ ] Run those tests and confirm they fail.
- [ ] Cache only after strict feasibility and AC validation; restore live fields from a deep copy on hit.
- [ ] Keep local iteration history and stopping checks unchanged on misses.
- [ ] Run focused tests and confirm passes.

### Task 3: Cache joint optimization results safely

**Files:**
- Modify: `src/simulation/engine.py` (`_run_joint_coordination`)
- Test: `tests/simulation/test_engine_optimization.py`, `tests/optimization/test_joint_coordination.py`

- [ ] Add tests for identical joint batches, changed renewable/load state, and AC-infeasible results.
- [ ] Run tests to confirm failure.
- [ ] Cache only the strictly feasible candidate after the existing AC validator accepts it; preserve the second tightened solve on validation failure.
- [ ] Restore assignments, start periods, power dispatch, and API payload through defensive copies.
- [ ] Run focused tests and confirm passes.

### Task 4: Verify full behavior and performance evidence

**Files:**
- Modify: `tests/simulation/test_engine_step.py` only if a regression test is needed.

- [ ] Run the relevant simulation and optimization tests.
- [ ] Run the complete pytest suite and record output.
- [ ] Compare before/after snapshots for all three modes on a fixed input, including assignments, controls, AC status, and report rows.
- [ ] Review the diff for unchanged solver settings and bounded cache behavior.
