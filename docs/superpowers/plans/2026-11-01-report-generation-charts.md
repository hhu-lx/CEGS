# 项目报告供需与任务功率图 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 只更新项目内生成的 SVG 报告，不改网页前端，新增供需/储能对照图和计划/实际任务功率对照图。

**Architecture:** 在 `SimulationEngine._record_stats` 中补充任务计划功率与实际功率统计字段；在报告生成函数中用统一时间轴生成两张 SVG。保留现有 `generation_24h.svg` 兼容输出，并将新图写入 `reports/`。

**Tech Stack:** Python、现有 SVG 字符串绘图、pytest。

**Spec:** `docs/superpowers/specs/2026-11-01-generation-net-load-design.md`

## Global Constraints

- 不修改网页前端设计或 JavaScript。
- 外网购电作为普通供电项，不突出显示。
- 计划风光不并入计划出力；实际风光单独展示。
- 储能正值表示放电，负值表示充电。

## Review Focus

- 计划任务时间窗跨越 24 小时边界时，曲线应按报告时间范围裁剪。
- 任务尚未实际启动时，实际功率应为 0，不应误算为计划功率。
- 没有任务或没有风光/储能数据时，SVG 仍应可生成。
- 负储能功率必须显示为充电，不被堆叠为正供给。
- 报告生成仍需保留 `generation_24h.svg` 与 `grid_power.svg` 兼容文件。

### Task 1: Extend statistics with planned and actual task power

**Files:**
- Modify: `src/simulation/engine.py` (`_record_stats`, report point assembly)
- Test: `tests/simulation/test_generation_report.py`

**Interfaces:**
- Produces per-record `planned_task_power_mw`, `actual_task_power_mw`, `planned_task_compute_tflops`, `actual_task_compute_tflops`.

- [ ] Add failing assertions for planned/actual fields using tasks with different submitted and actual start times.
- [ ] Implement time-window accumulation from task submission/plan duration and actual start/end, using each task's modeled power.
- [ ] Run the focused simulation report tests.

### Task 2: Generate the two project SVG reports

**Files:**
- Modify: `src/simulation/engine.py` report generation section
- Test: `tests/simulation/test_generation_report.py`

**Interfaces:**
- Produces `generation_24h.svg` (compatibility), `grid_power.svg` (alias), `supply_storage_24h.svg`, and `task_power_24h.svg` under the configured reports directory.

- [ ] Add failing checks for labels, colors, series names, and negative storage rendering.
- [ ] Implement muted palette and shared time-axis SVG helpers; include grid import as an ordinary series and actual wind/PV stacked with load/storage overlays.
- [ ] Implement planned-vs-actual task power chart with the same time scale.
- [ ] Run focused tests and inspect generated SVG text for expected series.

### Task 3: Full verification

- [ ] Run `pytest tests/simulation/test_generation_report.py -q`.
- [ ] Run the complete test suite with warnings disabled.
- [ ] Confirm no files under `src/web/` changed.

