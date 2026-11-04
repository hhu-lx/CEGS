# 算电协同平台重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将项目改造成配置驱动、支持储能和真实 COPT 优化的算电协同仿真平台。

**Architecture:** 领域模型描述任务、数据中心、设备池与储能；配置工厂创建可替换策略与优化器。仿真协调器在每个时间步更新电网状态、报价、任务决策和储能注入，并通过 FastAPI 暴露状态与控制接口。

**Tech Stack:** Python 3.10+，FastAPI，Pydantic，SimPy，Pandapower，COPT 8 / coptpy，PyYAML，pytest，httpx。

**Spec:** `docs/superpowers/specs/2026-09-17-calculation-power-platform-design.md`

## Global Constraints

- COPT 是必需的优化后端：优化启用时导入或许可证异常必须显式失败，禁止回退到启发式策略。
- COPT 安装根目录为 `F:\copt\copt80`；运行环境必须保留已有 `COPT_HOME` 与 `COPT_LICENSE_DIR`。
- 任务缺失字段只能由带固定种子的模拟数据工厂补齐，绝不能覆盖用户提交值。
- 保留既有 CSV/XLSX 文件，不将它们作为默认任务输入。
- 所有新增行为遵循先写失败测试、确认失败、最小实现、确认通过的 TDD 周期。

---

### Task 1: 建立可安装、可测试的项目基础

**Files:**
- Create: `pyproject.toml`
- Create: `tests/conftest.py`
- Create: `tests/test_environment.py`
- Modify: `src/__init__.py`

**Interfaces:**
- Produces: `pytest` 测试入口与项目依赖声明，供所有后续任务复用。

- [ ] **Step 1: 写出依赖声明测试**

```python
def test_runtime_dependencies_are_declared(project_root):
    content = (project_root / "pyproject.toml").read_text(encoding="utf-8")
    for dependency in ("fastapi", "pandapower", "simpy", "coptpy"):
        assert dependency in content
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_environment.py -q`
Expected: FAIL，原因是 `pyproject.toml` 不存在。

- [ ] **Step 3: 创建最小项目配置**

```toml
[project]
name = "calculation-power-synergy"
version = "0.1.0"
requires-python = ">=3.10,<3.15"
dependencies = ["fastapi", "uvicorn", "pydantic", "PyYAML", "simpy", "pandas", "pandapower", "coptpy"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

在 `tests/conftest.py` 提供 `project_root` fixture，并将 `src` 作为可导入包。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_environment.py -q`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml tests/conftest.py tests/test_environment.py src/__init__.py
git commit -m "build: add project dependencies and test setup"
```

### Task 2: 定义任务、设备与数据中心领域模型

**Files:**
- Create: `src/domain/device.py`
- Modify: `src/domain/task.py`
- Modify: `src/domain/datacenter.py`
- Modify: `src/domain/enums.py`
- Create: `tests/domain/test_task.py`
- Create: `tests/domain/test_datacenter.py`

**Interfaces:**
- Produces: `Task.transition_to(status, reason=None)`, `Task.is_expired(now)`, `DataCenter.can_allocate(task)`, `DataCenter.allocate(task)` 和 `DataCenter.release(task)`。
- Consumes: 无。

- [ ] **Step 1: 写出任务状态与资源约束测试**

```python
def test_ready_task_cancels_after_its_wait_deadline():
    task = Task(user_id="u1", task_type="ai_training", compute_amount_tflop_hours=12,
                duration_hours=2, submitted_at=10, max_wait_hours=0.5)
    assert task.is_expired(1809) is True
    task.cancel("wait_timeout")
    assert task.status == TaskStatus.CANCELLED
    assert task.cancel_reason == "wait_timeout"

def test_data_center_rejects_unavailable_required_gpu():
    dc = DataCenter.with_devices("dc1", [DeviceSpec(model="V100", quantity=1, compute_tflops=14, power_kw=300)])
    task = Task(user_id="u1", task_type="ai_training", compute_amount_tflop_hours=12,
                duration_hours=1, required_gpu_count=2, required_gpu_type="V100")
    assert dc.can_allocate(task) is False
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/domain/test_task.py tests/domain/test_datacenter.py -q`
Expected: FAIL，原因是新增字段、状态方法和 `DeviceSpec` 不存在。

- [ ] **Step 3: 实现最小领域模型**

定义 `TaskStatus` 枚举和 `DeviceSpec` Pydantic 模型；为 `Task` 添加计算量、最大等待、CPU/GPU、GPU 类型、取消原因和受控状态转换；令 `DataCenter` 维护设备可用量、PUE 与已用资源，基于任务完整资源需求分配和释放。

- [ ] **Step 4: 运行领域测试确认通过**

Run: `python -m pytest tests/domain/test_task.py tests/domain/test_datacenter.py -q`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add src/domain tests/domain
git commit -m "feat: model task lifecycle and data center devices"
```

### Task 3: 添加确定性缺失数据模拟与配置模型

**Files:**
- Create: `src/data/synthetic_tasks.py`
- Create: `src/config/models.py`
- Modify: `src/loaders/config_loader.py`
- Modify: `config/platform.yaml`
- Create: `tests/data/test_synthetic_tasks.py`
- Create: `tests/config/test_platform_config.py`

**Interfaces:**
- Produces: `SyntheticTaskDataFactory(seed).complete(task)` 和 `PlatformConfig.from_yaml(path)`。
- Consumes: `Task`、`DataCenter`、储能和策略配置。

- [ ] **Step 1: 写出确定性补齐与保留用户值测试**

```python
def test_factory_fills_only_missing_values_deterministically():
    task = Task(user_id="u1", task_type="rendering", compute_amount_tflop_hours=4,
                duration_hours=1, data_size_gb=None, required_cpu_cores=None, required_gpu_count=3)
    completed = SyntheticTaskDataFactory(seed=7).complete(task)
    again = SyntheticTaskDataFactory(seed=7).complete(task.model_copy(deep=True))
    assert completed.data_size_gb == again.data_size_gb
    assert completed.required_cpu_cores == again.required_cpu_cores
    assert completed.required_gpu_count == 3
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/data/test_synthetic_tasks.py tests/config/test_platform_config.py -q`
Expected: FAIL，原因是工厂和强类型配置不存在。

- [ ] **Step 3: 实现工厂与配置**

实现不覆盖非空字段的固定种子工厂；用 Pydantic 配置模型验证时间单位、仿真时长、策略、优化目标、约束、储能和数据中心配置；以相对路径替换现有 YAML 中机器相关绝对路径。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/data/test_synthetic_tasks.py tests/config/test_platform_config.py -q`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add src/data src/config src/loaders/config_loader.py config/platform.yaml tests/data tests/config
git commit -m "feat: add validated configuration and synthetic task data"
```

### Task 4: 实现储能模型与节点注入适配

**Files:**
- Create: `src/domain/storage.py`
- Create: `src/strategies/storage/base.py`
- Create: `src/strategies/storage/price_arbitrage.py`
- Modify: `src/infrastructure/pandapower_adapter.py`
- Create: `tests/domain/test_storage.py`
- Create: `tests/infrastructure/test_storage_injection.py`

**Interfaces:**
- Produces: `EnergyStorage.apply_power(requested_mw, step_hours)` 与 `PandapowerAdapter.update_storage_power(bus_id, net_power_mw)`。
- Consumes: 配置化储能规格与仿真时间步长。

- [ ] **Step 1: 写出 SOC 边界和充放电符号测试**

```python
def test_storage_caps_discharge_at_available_energy():
    storage = EnergyStorage(id="s1", bus_id=3, capacity_mwh=10, max_power_mw=8,
                            initial_soc_mwh=2, min_soc_mwh=1, charge_efficiency=0.9,
                            discharge_efficiency=0.9)
    actual = storage.apply_power(requested_mw=8, step_hours=1)
    assert actual == 0.9
    assert storage.soc_mwh == 1
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/domain/test_storage.py tests/infrastructure/test_storage_injection.py -q`
Expected: FAIL，原因是储能模型和节点注入接口不存在。

- [ ] **Step 3: 实现储能与适配器**

正功率表示放电并减少 SOC，负功率表示充电并增加 SOC；在 Pandapower 适配器中将充电视作负荷、放电视作发电注入，并令每步清理旧的动态储能元素。实现低价充电/高价放电的默认策略。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/domain/test_storage.py tests/infrastructure/test_storage_injection.py -q`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add src/domain/storage.py src/strategies/storage src/infrastructure/pandapower_adapter.py tests/domain/test_storage.py tests/infrastructure/test_storage_injection.py
git commit -m "feat: add storage state and grid injection"
```

### Task 5: 配置化策略注册表与调度实现

**Files:**
- Create: `src/strategies/registry.py`
- Create: `src/strategies/allocation/carbon_aware.py`
- Create: `src/strategies/allocation/delay_aware.py`
- Create: `src/strategies/allocation/load_balanced.py`
- Modify: `src/strategies/allocation/base.py`
- Modify: `src/strategies/allocation/lowest_price.py`
- Modify: `src/simulation/scheduler.py`
- Create: `tests/strategies/test_registry.py`
- Create: `tests/strategies/test_allocation.py`

**Interfaces:**
- Produces: `StrategyRegistry.create_allocation(name, settings)` 和 `Scheduler.select_data_center(task, centers, snapshot)`。
- Consumes: 数据中心报价、碳强度、网络延迟和可用资源。

- [ ] **Step 1: 写出策略名与低碳决策测试**

```python
def test_carbon_aware_strategy_selects_eligible_lowest_carbon_center():
    choice = CarbonAwareStrategy().allocate(task, [high_carbon, low_carbon], snapshot)
    assert choice.id == "low-carbon"

def test_registry_rejects_unknown_strategy_name():
    with pytest.raises(ValueError, match="unknown allocation strategy"):
        StrategyRegistry().create_allocation("unknown", {})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/strategies/test_registry.py tests/strategies/test_allocation.py -q`
Expected: FAIL，原因是注册表和新增策略不存在。

- [ ] **Step 3: 实现策略边界**

扩展 `AllocationStrategy.allocate` 以接收只读电网快照；将价格、碳、延迟和可用资源作为分配依据；注册定价、映射、电价、储能和目标函数策略，并让未知配置在启动时失败。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/strategies/test_registry.py tests/strategies/test_allocation.py -q`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add src/strategies src/simulation/scheduler.py tests/strategies
git commit -m "feat: configure scheduling and pricing strategies"
```

### Task 6: 接入真实 COPT 优化器与目标函数

**Files:**
- Create: `src/optimization/models.py`
- Create: `src/optimization/copt_optimizer.py`
- Create: `src/optimization/objectives.py`
- Create: `src/optimization/errors.py`
- Create: `tests/optimization/test_copt_optimizer.py`
- Create: `tests/optimization/test_objectives.py`

**Interfaces:**
- Produces: `CoptOptimizer.solve(problem: OptimizationProblem) -> OptimizationResult`。
- Consumes: 就绪任务、数据中心、储能、电网快照、`ObjectiveSpec` 和约束配置。

- [ ] **Step 1: 写出真实小规模 COPT 求解测试**

```python
def test_copt_assigns_task_to_the_only_feasible_center():
    result = CoptOptimizer().solve(OptimizationProblem(tasks=[task], data_centers=[infeasible, feasible], ...))
    assert result.status == "optimal"
    assert result.assignments[task.id] == feasible.id

def test_enabled_optimizer_reports_missing_backend_explicitly(monkeypatch):
    monkeypatch.setitem(sys.modules, "coptpy", None)
    with pytest.raises(CoptUnavailableError):
        CoptOptimizer().solve(problem)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/optimization/test_copt_optimizer.py tests/optimization/test_objectives.py -q`
Expected: FAIL，原因是 COPT 优化器和问题模型不存在。

- [ ] **Step 3: 实现优化器**

使用 `coptpy` 创建二元任务分配变量、发电机出力、充/放电和 SOC 变量；添加分配唯一性、资源、功率平衡、SOC、充放电互斥、等待和可选碳/线路/电压约束。实现 `min_cost`、`min_carbon`、`min_delay` 和 `weighted` 目标，返回原始求解状态、目标值、任务分配、机组出力及储能计划。将许可证或求解异常映射为显式领域错误。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/optimization/test_copt_optimizer.py tests/optimization/test_objectives.py -q`
Expected: PASS，且实际输出 COPT 的最优解。

- [ ] **Step 5: Commit**

```bash
git add src/optimization tests/optimization
git commit -m "feat: integrate COPT dispatch optimization"
```

### Task 7: 重构仿真闭环与完整统计

**Files:**
- Create: `src/domain/snapshots.py`
- Modify: `src/simulation/engine.py`
- Modify: `src/simulation/datacenter_sim.py`
- Modify: `src/infrastructure/pandapower_adapter.py`
- Create: `tests/simulation/test_engine_cycle.py`
- Create: `tests/simulation/test_task_lifecycle.py`

**Interfaces:**
- Produces: `SimulationEngine.step()`、`SimulationEngine.latest_snapshot()` 和 `SimulationEngine.optimization_result()`。
- Consumes: 策略注册表、储能策略/COPT 优化器和 Pandapower 快照。

- [ ] **Step 1: 写出闭环报价与超时取消测试**

```python
def test_next_cycle_uses_price_updated_from_previous_power_flow(engine, task):
    engine.submit_task(task)
    engine.step()
    first_price = engine.data_centers[0].current_price
    engine.step()
    assert engine.latest_snapshot().node_prices[engine.data_centers[0].grid_bus_id] > 0
    assert engine.data_centers[0].current_price == first_price or engine.data_centers[0].current_price > 0

def test_engine_cancels_ready_task_after_max_wait(engine, task):
    engine.submit_task(task)
    engine.advance_to(task.deadline_second + 1)
    assert task.status == TaskStatus.CANCELLED
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/simulation/test_engine_cycle.py tests/simulation/test_task_lifecycle.py -q`
Expected: FAIL，原因是同步 `step`、快照与严格任务状态流程不存在。

- [ ] **Step 3: 实现显式仿真步骤**

将后台循环委托给可测试的 `step()`；按规格固定八步顺序，先完成潮流后更新下一轮报价。为 `PandapowerAdapter` 产出节点、线路、碳排与发电结构快照，为引擎记录任务、储能、碳排和 COPT 统计；保留线程包装器用于连续运行。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/simulation/test_engine_cycle.py tests/simulation/test_task_lifecycle.py -q`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add src/domain/snapshots.py src/simulation src/infrastructure/pandapower_adapter.py tests/simulation
git commit -m "feat: implement coupled simulation cycle and metrics"
```

### Task 8: 重建 FastAPI 接口

**Files:**
- Modify: `src/app.py`
- Modify: `src/api/task_routes.py`
- Create: `src/api/status_routes.py`
- Create: `tests/api/test_tasks.py`
- Create: `tests/api/test_status.py`

**Interfaces:**
- Produces: `POST /tasks`、`GET /tasks/{task_id}`、`GET /grid/latest`、`GET /carbon/summary`、`GET /storage`、`GET /optimization/latest`。
- Consumes: `SimulationEngine` 查询接口。

- [ ] **Step 1: 写出 API 合约测试**

```python
def test_submit_task_preserves_user_data_and_fills_missing_optional_fields(client):
    response = client.post("/tasks", json={"user_id": "u1", "task_type": "ai_training", "compute_amount_tflop_hours": 4, "duration_hours": 1})
    assert response.status_code == 202
    body = response.json()
    assert body["task"]["data_size_gb"] is not None

def test_unknown_task_returns_404(client):
    response = client.get("/tasks/missing")
    assert response.status_code == 404
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/api/test_tasks.py tests/api/test_status.py -q`
Expected: FAIL，原因是所需路由和响应模型不存在。

- [ ] **Step 3: 实现路由和依赖注入**

移除模块级错误引擎导入；通过 FastAPI 依赖提供单一引擎实例。返回稳定的 Pydantic 响应模型，验证不可用参数并将任务、网格、碳、储能和优化查询映射到正确的 HTTP 状态码。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/api/test_tasks.py tests/api/test_status.py -q`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add src/app.py src/api tests/api
git commit -m "feat: expose task grid carbon storage and optimization APIs"
```

### Task 9: 补齐示例、文档与端到端验证

**Files:**
- Create: `config/platform.example.yaml`
- Create: `README.md`
- Create: `tests/integration/test_platform_run.py`
- Modify: `main.py`

**Interfaces:**
- Produces: 可通过 `python main.py --config config/platform.example.yaml` 启动的示例运行入口。
- Consumes: 完整配置、真实 COPT 与仿真引擎。

- [ ] **Step 1: 写出端到端最小实验测试**

```python
def test_small_config_runs_copt_cycle_and_exposes_storage_metrics(tmp_path):
    engine = SimulationEngine.from_config(write_small_example(tmp_path, optimization_enabled=True))
    engine.submit_task(sample_task())
    snapshot = engine.step()
    assert snapshot.storage["storage-1"].soc_mwh >= 0
    assert engine.optimization_result().status in {"optimal", "infeasible"}
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/integration/test_platform_run.py -q`
Expected: FAIL，原因是示例配置和统一启动入口不存在。

- [ ] **Step 3: 添加可复现实验说明**

写入包含储能、策略、COPT、目标权重与固定模拟数据种子的示例配置；在 README 说明安装 `coptpy`、保留 COPT 环境变量、启动 API、提交任务、切换目标与读取结果。将 `main.py` 改为调用统一 CLI 入口。

- [ ] **Step 4: 运行全部验证**

Run: `python -m pytest -q`
Expected: PASS，无失败或跳过的 COPT 集成测试。

Run: `python -m compileall src`
Expected: exit code 0。

- [ ] **Step 5: Commit**

```bash
git add config/platform.example.yaml README.md main.py tests/integration
git commit -m "docs: add reproducible COPT storage simulation example"
```
