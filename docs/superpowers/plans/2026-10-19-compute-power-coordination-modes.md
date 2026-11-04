# 算电协同三模式 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让启发式、局部优化和全局优化都真实优化常规机组、风光和储能，并以无协同、分解迭代协同、联合协同三种不同运行链执行，同时让前端只展示当前模式有效的策略与目标。

**Architecture:** 新增统一的模式能力表与电力调度结果接口；电力调度器负责滚动优化机组、风光和储能，局部协调器负责算力/电力交替迭代，联合协调器负责同模求解。`SimulationEngine` 只负责选择运行链，`PandapowerAdapter` 负责应用决策和 AC 校验，前端与 API 使用同一组模式约束语义。

**Tech Stack:** Python 3.11、FastAPI、Pydantic、SimPy、pandapower、COPT/coptpy、原生 HTML/CSS/JavaScript、Node.js `node:test`、pytest。

**Spec:** `docs/superpowers/specs/2026-10-19-compute-power-coordination-modes-design.md`

## Global Constraints

- 三种模式都必须考虑常规机组、风电、光伏和储能。
- 启发式不得使用电价、碳强度、电网状态反馈改变任务分配。
- 局部优化最多迭代 5 轮，目标相对变化不超过 `1e-3` 或任务分配连续两轮不变时终止。
- 全局优化的任务与电力决策必须来自同一个 COPT 模型。
- 电力决策应用后必须通过 AC 潮流校验；失败时不得把约束违背结果标记为可行。
- 电力规划窗口为未来 24 小时、1 小时粒度；秒级仿真只应用滚动窗口第一段决策。
- 前端先选择优化模型，再展示当前模型支持的策略与目标；后端必须独立重复校验。
- 当前工作目录不是 Git 仓库，因此各任务以测试通过和变更清单作为检查点，不执行虚假的提交步骤。

## Review Focus

- 用户从局部切到启发式后，隐藏的自定义调度文件和时延权重不得继续提交；Task 2 添加切换残留测试。
- 24 小时预测数据不足时必须循环补齐且记录 `forecast_fill=cyclic`；Task 4 添加短序列测试。
- 机组参数缺失、NaN 或上下限倒置时必须使用有来源标记的默认值或拒绝配置；Task 3 添加参数规范化测试。
- COPT 严格模型不可行或 AC 校验失败时必须保留上一严格可行点；Task 5、6、7 添加回退测试。
- 多数据中心、多储能和动态拓扑数量不得写死；Task 4、8 添加动态规模测试。

---

## File Structure

### New files

- `src/optimization/mode_capabilities.py`：后端模式、调度策略和目标兼容性定义与校验。
- `src/optimization/power_dispatch.py`：机组/风光/储能滚动优化数据模型与 COPT 求解器。
- `src/optimization/local_coordination.py`：算力与电力子问题的交替迭代控制器。
- `src/optimization/joint_coordination.py`：任务与电力变量的联合 COPT 模型。
- `src/web/mode_capabilities.js`：前端模式能力表、状态恢复和规范化提交值。
- `tests/optimization/test_mode_capabilities.py`
- `tests/optimization/test_power_dispatch.py`
- `tests/optimization/test_local_coordination.py`
- `tests/optimization/test_joint_coordination.py`
- `tests/web/mode_capabilities.test.js`

### Modified files

- `src/api/frontend_routes.py`：应用配置时校验模式组合，导出完整优化结果。
- `src/config/models.py`：增加电力优化、滚动窗口和机组默认参数配置。
- `src/loaders/topology_loader.py`：读取和规范化机组成本、排放、爬坡参数。
- `src/infrastructure/pandapower_adapter.py`：提供电力调度输入、应用机组级决策、AC 校验和安全反馈。
- `src/optimization/copt_optimizer.py`：复用任务变量构建逻辑并传入真实时延/碳信号。
- `src/simulation/engine.py`：按模式调用启发式、局部、联合三条运行链。
- `src/web/index.html`：优化模型前置，增加只读策略卡和电力目标选项。
- `src/web/app.js`：模型切换时动态渲染、清理无效字段并规范化提交。
- `src/web/styles.css`：只读策略卡、隐藏状态与禁用权重样式。
- `tests/api/test_frontend_routes.py`
- `tests/infrastructure/test_storage_injection.py`
- `tests/simulation/test_engine_optimization.py`
- `tests/simulation/test_storage_step.py`

---

### Task 1: 后端模式能力与组合校验

**Files:**
- Create: `src/optimization/mode_capabilities.py`
- Create: `tests/optimization/test_mode_capabilities.py`
- Modify: `src/api/frontend_routes.py:219-255,376-428`
- Test: `tests/api/test_frontend_routes.py`

**Interfaces:**
- Produces: `ModeCapabilities`, `capabilities_for(mode: str) -> ModeCapabilities`、`normalise_frontend_selection(mode: str, dispatch: str | None, objective: str) -> NormalizedSelection`。
- `NormalizedSelection` fields: `mode`, `dispatch_strategy`, `objective`, `dispatch_managed_by`。

- [ ] **Step 1: Write failing capability tests**

Add tests asserting:

```python
assert capabilities_for("heuristic").fixed_dispatch == "load_balance"
assert "min_delay" not in capabilities_for("heuristic").objectives
assert "min_delay" in capabilities_for("local").objectives
assert capabilities_for("global").fixed_dispatch == "optimizer_managed"
```

- [ ] **Step 2: Run the new tests and verify RED**

Run: `F:\python\python.exe -m pytest -q tests\optimization\test_mode_capabilities.py`

Expected: FAIL because `src.optimization.mode_capabilities` does not exist.

- [ ] **Step 3: Implement immutable capability definitions**

Implement exact public names above. Supported objectives are `min_cost`, `min_carbon`, `min_curtailment`, `peak_shaving`, `min_delay`, `weighted`, `custom`. Only local exposes all five dispatch choices; heuristic normalizes to `load_balance`, global to `optimizer_managed`.

- [ ] **Step 4: Add failing API validation tests**

Test `/config/apply` rejects `heuristic + min_delay`, rejects `global + custom dispatch`, and returns normalized `dispatch_managed_by` for valid heuristic/global requests. Expect HTTP 422 for incompatible direct API combinations.

- [ ] **Step 5: Integrate validation in `FrontendSession.apply`**

Validate before building `ui_config`. Keep `configuration.dispatch_strategy` equal to the normalized effective value, not the stale submitted value. For global mode, use an internal load-balanced scheduler object solely to satisfy engine construction while reporting `dispatch_managed_by="joint_optimizer"`.

- [ ] **Step 6: Verify Task 1**

Run: `F:\python\python.exe -m pytest -q tests\optimization\test_mode_capabilities.py tests\api\test_frontend_routes.py`

Expected: PASS.

### Task 2: 模型优先的前端动态选择

**Files:**
- Create: `src/web/mode_capabilities.js`
- Create: `tests/web/mode_capabilities.test.js`
- Modify: `src/web/index.html:14-27`
- Modify: `src/web/app.js:260-365`
- Modify: `src/web/styles.css`

**Interfaces:**
- Consumes: mode names and strategy/objective names from Task 1.
- Produces: `capabilitiesFor(mode)`、`selectionForMode(previousByMode, mode)`、`payloadForMode(values)` as UMD exports usable by browser and `node:test`.

- [ ] **Step 1: Write failing JavaScript capability tests**

Cover heuristic read-only load balance, local full dispatch list, global optimizer-managed dispatch, per-mode selection restoration, and removal of hidden custom file/config fields.

- [ ] **Step 2: Run and verify RED**

Run: `node --test tests/web/mode_capabilities.test.js`

Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement `mode_capabilities.js`**

Use one frozen capability map. `payloadForMode` must never emit `custom_dispatch_config` outside local mode and must never emit delay/custom delay weight in heuristic mode.

- [ ] **Step 4: Reorder and render the form**

Move optimization model to step 5. Replace dispatch select with a container that renders either a select or a read-only explanation card. Populate objective options from the capability map; keep pricing visible in all modes.

- [ ] **Step 5: Wire switching and normalized submission**

In `app.js`, store compatible selections per mode, refresh panels immediately on model change, and build `FormData` only from `payloadForMode` output. Do not read hidden input values directly.

- [ ] **Step 6: Verify frontend tests**

Run: `node --test tests/web/*.test.js`

Expected: all tests PASS.

### Task 3: 机组参数规范化与拓扑兼容

**Files:**
- Modify: `src/loaders/topology_loader.py`
- Modify: `src/config/models.py`
- Test: `tests/loaders/test_topology_loader.py`
- Test: `tests/api/test_frontend_topology.py`

**Interfaces:**
- Produces: `normalise_generator_parameters(generator: dict, defaults: GeneratorDefaults) -> dict` and normalized generator entries containing `ramp_up_mw_per_hour`, `ramp_down_mw_per_hour`, `cost_linear_yuan_per_mwh`, `cost_quadratic_yuan_per_mw2h`, `emission_tco2_per_mwh`, `parameter_sources`.

- [ ] **Step 1: Write failing topology tests**

Test user-provided values are preserved; missing values receive documented defaults; NaN/non-numeric values fail; `min_p_mw > max_p_mw` fails; default source names appear in `parameter_sources`.

- [ ] **Step 2: Run and verify RED**

Run: `F:\python\python.exe -m pytest -q tests\loaders\test_topology_loader.py tests\api\test_frontend_topology.py`

Expected: new assertions FAIL.

- [ ] **Step 3: Implement normalization and configuration models**

Default ramp up/down is `0.5 * max_p_mw` per hour. Cost/emission defaults come from a fixed platform generator-type table keyed by the existing topology generator classification; unknown types use an explicitly named `generic_thermal` row.

- [ ] **Step 4: Verify Task 3**

Run the Task 3 command again. Expected: PASS.

### Task 4: 统一滚动电力调度器

**Files:**
- Create: `src/optimization/power_dispatch.py`
- Create: `tests/optimization/test_power_dispatch.py`

**Interfaces:**
- Produces dataclasses `GeneratorDispatchInput`, `RenewableForecast`, `StorageDispatchInput`, `PowerDispatchProblem`, `PowerDispatchResult`.
- Produces `PowerDispatchOptimizer.solve(problem: PowerDispatchProblem) -> PowerDispatchResult`.
- `PowerDispatchResult` fields include `status`, `objective_value`, `generator_mw`, `renewable_dispatched_mw`, `renewable_curtailed_mw`, `storage_power_mw`, `storage_soc_mwh`, `objective_components`, `strictly_feasible`, `forecast_fill`.

- [ ] **Step 1: Write failing one-period feasibility tests**

Assert exact power balance, generator bounds, renewable limits, storage SOC bounds, and dynamic numbers of generators/storages.

- [ ] **Step 2: Write failing objective tests**

Use a two-generator fixture where `min_cost` selects the cheap dirty unit and `min_carbon` selects the costly clean unit. Add curtailment and peak-shaving fixtures that produce different dispatches.

- [ ] **Step 3: Write failing rolling-window tests**

Assert a 24-period case charges before a peak and discharges at the peak; a 3-point forecast is cyclically expanded to 24 points and reports `forecast_fill="cyclic"`; ramp constraints bind between periods.

- [ ] **Step 4: Run and verify RED**

Run: `F:\python\python.exe -m pytest -q tests\optimization\test_power_dispatch.py`

Expected: FAIL because the module does not exist.

- [ ] **Step 5: Implement COPT model**

Build generator, renewable, storage charge/discharge/mode/SOC variables for 24 hourly periods. Enforce all Global Constraints. Keep feasibility slack disabled in the strict solve; expose a separate diagnostic solve only when strict solve fails, and never set `strictly_feasible=True` for it.

- [ ] **Step 6: Implement normalized objective components**

Support the exact objective names from Task 1. Normalize each component by a deterministic positive reference derived from problem bounds; return raw and normalized components so reports remain interpretable.

- [ ] **Step 7: Verify Task 4**

Run the Task 4 test command. Expected: PASS with no warnings.

### Task 5: Pandapower 决策应用与 AC 校验

**Files:**
- Modify: `src/infrastructure/pandapower_adapter.py:92-229,309-325,464-617`
- Modify: `tests/infrastructure/test_storage_injection.py`
- Create or Modify: `tests/infrastructure/test_power_dispatch_application.py`

**Interfaces:**
- Consumes: `PowerDispatchResult` from Task 4.
- Produces: `build_power_dispatch_problem(second: int, horizon_hours: int = 24) -> PowerDispatchProblem`、`apply_power_dispatch(result: PowerDispatchResult, period: int = 0) -> dict`、`validate_dispatch_ac() -> dict`、`restore_last_feasible_dispatch() -> bool`.

- [ ] **Step 1: Write failing adapter application tests**

Assert per-generator `p_mw`, renewable dispatch and storage power are applied from period zero; the number of generators and storages is dynamic; base-generation data is present as a reference trajectory rather than directly overwriting optimized output.

- [ ] **Step 2: Write failing rollback tests**

Apply a known feasible result, then an AC-invalid result. Assert rollback restores every generator, renewable and storage value and returns the prior dispatch identifier.

- [ ] **Step 3: Run and verify RED**

Run: `F:\python\python.exe -m pytest -q tests\infrastructure\test_power_dispatch_application.py tests\infrastructure\test_storage_injection.py`

Expected: new tests FAIL.

- [ ] **Step 4: Implement adapter interfaces**

Separate forecast/reference loading from actual dispatch application. `run_power_flow` remains the AC validator; it no longer decides normal generator output by proportional scaling after an optimized point exists.

- [ ] **Step 5: Verify Task 5**

Run Task 5 tests. Expected: PASS.

### Task 6: 启发式无协同运行链

**Files:**
- Modify: `src/simulation/engine.py:580-695,756-827,878-1103`
- Modify: `tests/simulation/test_engine_optimization.py`
- Modify: `tests/simulation/test_storage_step.py`

**Interfaces:**
- Consumes: `PowerDispatchOptimizer`, adapter interfaces and normalized mode selection.
- Produces: `SimulationEngine._run_heuristic_cycle() -> dict` and `latest_power_dispatch_result`.

- [ ] **Step 1: Write failing no-coordination test**

Run identical tasks twice with different price/carbon/renewable signals. Assert heuristic task assignments stay identical while generator, renewable or storage dispatch changes.

- [ ] **Step 2: Write failing electrical-participation test**

Assert heuristic results contain non-empty `generator_mw`, renewable dispatched/curtailed values and storage SOC, and satisfy strict power balance.

- [ ] **Step 3: Run and verify RED**

Run: `F:\python\python.exe -m pytest -q tests\simulation\test_engine_optimization.py tests\simulation\test_storage_step.py`

Expected: new tests FAIL.

- [ ] **Step 4: Implement heuristic cycle**

Keep FCFS/resource load-balance task dispatch. After current task load is known, solve the power problem, apply period zero, run AC validation, and restore the previous feasible dispatch on failure. Do not feed any electrical signal back to task assignment.

- [ ] **Step 5: Verify Task 6**

Run Task 6 tests. Expected: PASS.

### Task 7: 局部分解迭代协调器

**Files:**
- Create: `src/optimization/local_coordination.py`
- Create: `tests/optimization/test_local_coordination.py`
- Modify: `src/simulation/engine.py`
- Modify: `src/optimization/copt_optimizer.py:39-142`

**Interfaces:**
- Produces `LocalCoordinationResult` with `status`, `assignments`, `power_dispatch`, `iterations`, `converged`, `objective_history`.
- Produces `LocalCoordinationOptimizer.solve(tasks, data_centers, task_context, power_problem_factory, *, max_iterations=5, tolerance=1e-3) -> LocalCoordinationResult`.

- [ ] **Step 1: Write failing feedback/convergence tests**

Use deterministic fake subproblem solvers to assert feedback order, maximum 5 iterations, tolerance `1e-3`, and early stop after identical assignments in two consecutive rounds.

- [ ] **Step 2: Write failing infeasibility preservation test**

If iteration 3 is infeasible, assert iteration 2's strict feasible assignment and power dispatch are returned; if iteration 1 is infeasible, assert tasks remain queued.

- [ ] **Step 3: Run and verify RED**

Run: `F:\python\python.exe -m pytest -q tests\optimization\test_local_coordination.py`

Expected: FAIL because the module does not exist.

- [ ] **Step 4: Implement coordinator**

Pass current nodal prices, nodal carbon values, latency matrix and grid capacity signals into each task solve. Build the next power problem from the resulting data-center loads and feed validated electrical signals into the following round.

- [ ] **Step 5: Integrate local mode**

Replace the existing one-pass fixed-placement COPT validation in hierarchical mode with `LocalCoordinationOptimizer`. Preserve queue fairness, user-specified data centers and resource reservation rules.

- [ ] **Step 6: Verify Task 7**

Run: `F:\python\python.exe -m pytest -q tests\optimization\test_local_coordination.py tests\simulation\test_engine_optimization.py`

Expected: PASS.

### Task 8: 全局联合协调器

**Files:**
- Create: `src/optimization/joint_coordination.py`
- Create: `tests/optimization/test_joint_coordination.py`
- Modify: `src/optimization/copt_optimizer.py`
- Modify: `src/simulation/engine.py`

**Interfaces:**
- Produces `JointCoordinationResult` with task assignments/start periods plus the complete `PowerDispatchResult` fields.
- Produces `JointCoordinationOptimizer.solve(tasks, data_centers, power_problem, *, objective, weights, latency_ms, carbon_intensity) -> JointCoordinationResult`.

- [ ] **Step 1: Write failing joint-model tests**

Construct a two-center/two-generator case where cheap renewable power at one node changes task placement. Assert task assignment and generator/renewable/storage decisions come from one solve and power balance includes selected data-center load.

- [ ] **Step 2: Write failing resource and timing tests**

Assert compute, bandwidth, GPU, submitted-at, duration and max-wait constraints; include dynamic data-center counts and a task that must remain queued when no strict feasible placement exists.

- [ ] **Step 3: Write failing AC-retry test**

Simulate one failed AC validation and one successful tightened solve. Assert only the successful result is applied; if both fail, restore the last strict feasible point.

- [ ] **Step 4: Run and verify RED**

Run: `F:\python\python.exe -m pytest -q tests\optimization\test_joint_coordination.py`

Expected: FAIL because the module does not exist.

- [ ] **Step 5: Implement the unified COPT model**

Reuse Task 4 variable/objective builders rather than solving `assign_tasks` and power dispatch separately. Include task-to-center/time binary variables directly in the nodal/data-center load expressions.

- [ ] **Step 6: Integrate joint mode**

Remove the current `global_optimize` wrapper path that only optimizes task assignment. Route global mode through `JointCoordinationOptimizer` and keep independent dispatch strategy disabled.

- [ ] **Step 7: Verify Task 8**

Run: `F:\python\python.exe -m pytest -q tests\optimization\test_joint_coordination.py tests\simulation\test_engine_optimization.py`

Expected: PASS.

### Task 9: 结果、完整导出与端到端验收

**Files:**
- Modify: `src/simulation/engine.py:1105-1320`
- Modify: `src/api/frontend_routes.py:351-369,451-476`
- Modify: `src/web/app.js`
- Modify: `tests/api/test_status.py`
- Modify: `tests/api/test_frontend_routes.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: all three mode result types.
- Produces stable status fields `coordination_mode`, `coordination_iterations`, `generator_dispatch`, `objective_components`, `strictly_feasible`, and complete-history CSV/XLSX/JSON export.

- [ ] **Step 1: Write failing status/export tests**

Assert status exposes mode-specific iteration and generator fields; export contains more than one statistics time point; dynamic generator/data-center/storage IDs become columns or normalized rows without hard-coded counts.

- [ ] **Step 2: Run and verify RED**

Run: `F:\python\python.exe -m pytest -q tests\api\test_status.py tests\api\test_frontend_routes.py`

Expected: new assertions FAIL.

- [ ] **Step 3: Persist complete optimization history**

Record one structured entry per reported time point. Keep the existing latest snapshot API for dashboard compatibility and use complete history for exports.

- [ ] **Step 4: Update frontend state labels**

Show the effective mode and optimization status without reintroducing hidden invalid selections. Keep chart series dynamic for user-defined data centers and devices.

- [ ] **Step 5: Update README configuration and experiment instructions**

Document the three mathematical meanings, generator optional fields, default sources, rolling window and valid frontend combinations.

- [ ] **Step 6: Run focused end-to-end tests**

Run: `F:\python\python.exe -m pytest -q tests\optimization tests\simulation tests\infrastructure tests\api`

Expected: PASS.

### Task 10: Full verification

**Files:**
- Verify all modified files; no new production behavior in this task.

- [ ] **Step 1: Run complete Python suite**

Run: `F:\python\python.exe -m pytest -q --disable-warnings`

Expected: all tests PASS; report any pre-existing background-thread encoding warning separately if it still occurs.

- [ ] **Step 2: Run complete JavaScript suite**

Run: `node --test tests/web/*.test.js`

Expected: all tests PASS.

- [ ] **Step 3: Run syntax compilation**

Run: `F:\python\python.exe -m compileall -q src`

Expected: exit code 0.

- [ ] **Step 4: Verify requirements against the spec**

Check every item in spec sections 3, 5, 7, 9 and 10 against tests and runtime fields. Record any deferred item explicitly; do not describe a partial implementation as complete.

- [ ] **Step 5: Request final code review**

Review specifically for silent option overrides, non-strict feasibility being reported as success, hard-coded device counts, stale mode selections and differences between the implemented math and paper terminology.
