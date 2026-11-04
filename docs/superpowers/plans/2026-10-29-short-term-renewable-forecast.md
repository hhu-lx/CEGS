# 短期新能源滚动预测 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 根据当前时刻以前的实际风光出力生成短期预测，并让全局优化使用预测序列进行任务时间转移。

**Architecture:** 新增无状态的短期预测器，接收观测序列、当前源数据位置、预测步长和预测长度。适配器在构造电力调度问题时调用预测器；实际网络注入和统计仍使用实时观测值。CSV 继续作为实际观测源。

**Tech Stack:** Python、NumPy、现有 `TimeSeriesDataLoader`、COPT 联合优化模型。

**Spec:** `docs/superpowers/specs/2026-10-29-short-term-renewable-forecast-design.md`

## Global Constraints

- 不读取当前时刻之后的观测值生成预测。
- 风光预测必须非负且不超过对应装机容量。
- 现有配置和直接节点 MW 文件保持兼容。
- 实际发电统计继续使用实际出力，不使用预测值。

## Review Focus

- 仿真开始时历史不足：应使用当前观测和物理边界回退。
- 光伏夜间与日出日落：应保持零值和合理爬坡。
- 风电短时波动：应满足相邻预测点的变化速率限制。
- 直接节点 MW 文件：预测应保持 MW 单位，不重复乘装机容量。
- 预测长度不足或数据异常：应返回完整长度的安全序列。

### Task 1: 短期预测器

**Files:**
- Create: `src/optimization/renewable_forecast.py`
- Test: `tests/optimization/test_renewable_forecast.py`

- [ ] 写测试：历史截断、非负边界、光伏夜间为零、风电爬坡限制和长度完整。
- [ ] 运行预测器测试，确认在模块不存在前失败。
- [ ] 实现 `ShortTermRenewableForecaster.forecast(...)`，使用历史平滑、趋势和物理边界。
- [ ] 运行预测器测试，确认通过。

### Task 2: 接入电力调度问题

**Files:**
- Modify: `src/infrastructure/pandapower_adapter.py`
- Test: `tests/infrastructure/test_renewable_forecast_integration.py`

- [ ] 写测试：构造调度问题时，预测值不等于当前时刻之后的观测值，并保持风光单位。
- [ ] 运行集成测试确认当前实现直接读取未来值。
- [ ] 接入预测器，按调度问题的时间步长生成风光预测。
- [ ] 保留直接拓扑 MW 文件的单位和实际注入逻辑。
- [ ] 运行集成测试确认预测来自历史截断。

### Task 3: 联合优化回归

**Files:**
- Test: `tests/optimization/test_joint_coordination.py`
- Test: `tests/simulation/test_engine_optimization.py`

- [ ] 增加一个任务可延后的场景，确认联合模型能读取未来预测并返回非零启动偏移。
- [ ] 运行联合优化和仿真相关测试。
- [ ] 检查实际风光统计仍使用 dispatched/curtailed 值。
