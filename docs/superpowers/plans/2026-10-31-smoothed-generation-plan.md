# 平滑出力计划 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 从现有常规出力计划生成平滑的新计划文件，不改变负荷和风光数据。

**Architecture:** 通过独立数据处理脚本读取旧的一列标幺值计划，执行滚动中位数和滚动均值平滑，保持原计划均值并裁剪到 `[0,1]`。配置切换到新文件，旧文件保留。

**Tech Stack:** Python、NumPy、Pandas、Pytest、YAML 配置。

**Spec:** `docs/superpowers/specs/2026-10-31-smoothed-generation-plan-design.md`

## Global Constraints

- 负荷、风电、光伏输入文件不修改。
- 新计划必须是一秒一个点，并与旧计划长度一致。
- 不增加第三方依赖。

## Review Focus

- 孤立小尖峰应被消除，而不是把 24 小时趋势抹平。
- 输出均值不能因为平滑发生明显漂移。
- 文件长度、有限性和标幺值边界必须保持有效。
- 配置切换后程序必须读取新文件。

### Task 1: Add deterministic smoothing utility and regression tests

**Files:**
- Create: `scripts/smooth_generation_plan.py`
- Test: `tests/data/test_smooth_generation_plan.py`

**Interfaces:**
- Produces `smooth_generation_plan(values, median_window_seconds=61, mean_window_seconds=601) -> np.ndarray`.
- Script reads `config/base_generation_pu_second.csv` and writes `config/base_generation_pu_second_smoothed.csv`.

- [ ] Write tests for length/bounds, mean preservation, and suppression of an isolated spike.
- [ ] Implement rolling median, rolling mean, mean-offset correction, and `[0,1]` clipping.
- [ ] Run the focused tests.

### Task 2: Generate and activate the new plan

**Files:**
- Modify: `config/platform.yaml`
- Modify: `config/platform.example.yaml`
- Create: `config/base_generation_pu_second_smoothed.csv`

- [ ] Run the smoothing script against the current plan.
- [ ] Verify the new file has 86,400 rows and no invalid values.
- [ ] Switch both platform configs to the new file while retaining the old file.

### Task 3: Verify integration

- [ ] Run focused data/config tests and Python compilation.
- [ ] Compare old/new mean, standard deviation, and maximum one-second change; report the results.
