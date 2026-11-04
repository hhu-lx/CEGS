# 仿真加速实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将潮流计算周期扩大到 5 分钟并消除高频无效工作，同时保证任务不漏调度。

**Architecture:** 在 `SimulationEngine.step()` 统一控制完整潮流刷新，新能源复用只更新出力；任务提交队列利用排序前缀，调度队列采用基于上次扫描时间的到期判断；`DataCenterSim` 用主步长推进任务进度。

**Tech Stack:** Python、SimPy、pandapower、pytest。

**Spec:** `docs/superpowers/specs/2026-10-23-simulation-speedup-design.md`

## Global Constraints

- 完整潮流计算周期默认为 300 仿真秒。
- 不得因周期跨越或步长不整除而漏掉可调度任务。
- 保留任务结束时间的精确截断。

## Review Focus

- `step_seconds` 大于 1 时，任务不能被每秒事件链拖慢。
- 当前秒跨过调度批次边界时，队列必须触发扫描。
- 待提交任务已按时间排序时，未来任务不能提前释放。
- 新能源复用不能重复调用潮流。
- 任务启动/结束的电网状态更新仍保持一致。

### Task 1: 潮流与新能源复用解耦

**Files:** `src/simulation/engine.py`, `config/platform.yaml`, `config/platform.example.yaml`, `tests/simulation/test_engine_step.py`, `tests/simulation/test_engine_renewable_dispatch.py`

- [ ] 写测试：复用出力不调用潮流；步进在 300 秒周期内只按周期触发潮流。
- [ ] 运行测试确认先失败。
- [ ] 修改实现和默认配置。
- [ ] 运行相关测试确认通过。

### Task 2: 任务释放与调度周期鲁棒性

**Files:** `src/simulation/engine.py`, `tests/simulation/test_engine_optimization.py`

- [ ] 写测试：排序队列只释放到达前缀；步长跨过批次边界仍扫描调度队列。
- [ ] 运行测试确认先失败。
- [ ] 用到期时间记录替代取模判断。
- [ ] 运行相关测试确认通过。

### Task 3: 任务执行事件按主步长推进

**Files:** `src/simulation/datacenter_sim.py`, `tests/simulation/test_storage_step.py` 或新增任务执行测试。

- [ ] 写测试：主步长为 5 秒时，任务执行不会退化为 1 秒事件，同时结束秒精确。
- [ ] 运行测试确认先失败。
- [ ] 使用 `step_seconds` 作为任务过程步长并保留剩余时间截断。
- [ ] 运行相关测试确认通过。

### Task 4: 全量验证

- [ ] 运行完整 pytest 套件。
- [ ] 检查配置、测试和代码差异，确认没有修改用户数据或无关行为。
