# 全局优化储能与堆叠发电图 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让全局优化更持续地使用储能削峰填谷，并将 24 小时发电图改成左上角图例的堆叠面积图。

**Architecture:** 新增全局优化适配文件，将全局目标转换为包含成本、风光弃电、峰值削减和储能退化的联合目标，并通过滚动窗口末端 SOC 保留避免储能提前耗尽；报告生成器只替换发电图绘制方式。

**Tech Stack:** Python、COPT、SVG、Pytest。

**Spec:** `docs/superpowers/specs/2026-10-31-global-storage-chart-design.md`

## Global Constraints

- 启发式和局部优化逻辑不改。
- 发电图的负荷、风电、光伏输入不改。
- 图例固定在左上角，但必须避免文字重叠。

## Review Focus

- 全局优化不能因新目标而失去严格可行性。
- 储能末端 SOC 约束不能超过物理上限或造成无任务时不可行。
- 堆叠分量应为非负供电分量，储能充电不应被错误计入发电。
- 零值或空历史时报告生成不能报错。

### Task 1: Isolate global objective policy

**Files:**
- Create: `src/optimization/global_coordination.py`
- Modify: `src/optimization/joint_coordination.py`
- Modify: `src/simulation/engine.py`
- Test: `tests/optimization/test_global_coordination.py`

- [ ] Write a test proving global policy adds peak-shaving/storage weights and a terminal SOC target while the base joint optimizer remains unchanged by default.
- [ ] Add optional terminal SOC target support to the joint model.
- [ ] Add `GlobalCoordinationOptimizer` adapter and use it only from `_run_joint_coordination`.
- [ ] Run focused optimizer tests.

### Task 2: Replace generation report with stacked chart

**Files:**
- Modify: `src/simulation/engine.py`
- Test: `tests/simulation/test_generation_report.py`

- [ ] Write tests for stacked SVG paths, left-top legend background, and no duplicated overlapping legend placement.
- [ ] Implement stacked area rendering for base, conventional, wind, PV, storage discharge, and grid import.
- [ ] Keep `grid_power.svg` as the compatibility alias.
- [ ] Run focused report tests.

### Task 3: Verify full integration

- [ ] Run focused optimizer/report tests and Python compilation.
- [ ] Check that local/heuristic paths still resolve to their existing optimizers.
