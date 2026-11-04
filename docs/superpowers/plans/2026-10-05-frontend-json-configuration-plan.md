# 前端 JSON 配置与 JSON 电力拓扑重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让前端通过 JSON 配置和上传文件创建仿真，并让 IEEE39/用户电力拓扑从 JSON 构建，同时保持旧 YAML 和命令行入口兼容。

**Architecture:** 新增用户配置加载与校验层，先将用户 JSON 与系统默认配置合并，再构建拓扑、数据中心、储能和仿真引擎。新增中立拓扑 JSON 加载器，将 bus、线路、变压器、负荷、发电机、新能源和储能转换为 Pandapower 网络；未提交用户拓扑时使用默认 IEEE39 JSON 模板。

**Tech Stack:** Python 3、标准库 `json/csv/pathlib`、PyYAML、Pandas、Pandapower、SimPy、COPT、Pytest。

**Spec:** `docs/superpowers/specs/2026-10-05-frontend-json-configuration-design.md`

## Global Constraints

- 用户不需要编辑 YAML 即可完成一次仿真配置。
- 配置优先级为：前端 JSON > 命令行参数 > 系统默认配置。
- 默认模拟数据保持 3 个数据中心和 1 个储能设备。
- 固定电价必须完整覆盖 `0–24` 小时，时段不能重叠或留空。
- 用户拓扑未提供时使用默认拓扑，用户拓扑提供后优先使用。
- 保留现有三种优化模式、用户目标函数接口、任务生命周期和输出格式。
- 只允许访问配置的上传目录、项目数据目录或明确的用户工作目录，禁止通过 `..` 越权访问。

## Review Focus

- 用户 JSON 缺少字段或字段类型错误时，启动前返回带字段路径的错误；由任务 1 的校验测试覆盖。
- 用户拓扑引用不存在的母线时，构建前拒绝；由任务 2 的拓扑校验测试覆盖。
- 用户拓扑存在时不能悄悄退回 IEEE39；由任务 3 的拓扑优先级测试覆盖。
- 多个数据中心和多个储能设备必须保持独立 ID 与资源约束；由任务 4 的构建测试覆盖。
- 旧 YAML/CLI 运行路径不能回归；由任务 5 的兼容性测试覆盖。

---

### Task 1: 用户 JSON 配置加载、合并与校验

**Files:**
- Create: `src/loaders/user_config_loader.py`
- Create: `tests/loaders/test_user_config_loader.py`
- Modify: `src/loaders/config_loader.py`

**Interfaces:**
- Produces `load_user_config(user_config_file: str | None = None, user_config: dict | None = None, defaults: dict | None = None) -> dict`。
- Produces `validate_user_config(config: dict) -> None`，错误使用包含字段路径的 `ValueError`。
- Produces `resolve_user_path(path: str, allowed_roots: list[Path]) -> Path`。

- [ ] **Step 1: 写失败测试**：覆盖 JSON 文件加载、字典加载、用户字段覆盖默认值、非法优化模式、固定电价时段缺口/重叠和 `..` 路径拒绝。
- [ ] **Step 2: 运行测试确认失败**：`pytest tests/loaders/test_user_config_loader.py -q`。
- [ ] **Step 3: 实现加载、深度合并、字段校验和安全路径解析**，不引入新的第三方依赖。
- [ ] **Step 4: 运行测试确认通过**：`pytest tests/loaders/test_user_config_loader.py -q`。
- [ ] **Step 5: 运行现有配置相关测试**：`pytest tests/strategies/test_fixed_tou_pricing.py tests/simulation/test_pricing_mode.py -q`。

### Task 2: JSON 拓扑格式、默认 IEEE39 模板与 Pandapower 构建器

**Files:**
- Create: `src/loaders/topology_loader.py`
- Create: `config/topology_ieee39.json`
- Create: `tests/loaders/test_topology_loader.py`
- Modify: `src/infrastructure/pandapower_adapter.py`

**Interfaces:**
- Produces `load_topology(path: str | Path) -> dict`。
- Produces `validate_topology(topology: dict) -> None`。
- Produces `build_pandapower_network(topology: dict)`，返回 `(network, bus_map)`。
- `PandapowerAdapter(..., topology: dict | None = None, topology_file: str | None = None)` 优先使用用户拓扑，未提供时加载默认 IEEE39 JSON。

- [ ] **Step 1: 写失败测试**：覆盖默认模板加载、bus/line/generator 构建、线路引用不存在母线时报错，以及用户拓扑替换默认拓扑。
- [ ] **Step 2: 运行测试确认失败**：`pytest tests/loaders/test_topology_loader.py -q`。
- [ ] **Step 3: 从当前 `pn.case39()` 导出等价默认 JSON 模板**，实现中立拓扑校验和 Pandapower 构建器。
- [ ] **Step 4: 修改 `PandapowerAdapter` 使用构建器**，保留新能源、基础发电、算力负荷和储能动态层逻辑。
- [ ] **Step 5: 运行测试确认通过**：`pytest tests/loaders/test_topology_loader.py tests/infrastructure/test_storage_injection.py -q`。

### Task 3: 用户配置驱动的数据中心与储能构建

**Files:**
- Modify: `src/loaders/config_loader.py`
- Modify: `src/simulation/engine.py`
- Create: `tests/loaders/test_user_resources.py`

**Interfaces:**
- `build_data_centers(config: dict)` 从合并后的用户配置读取数据中心列表；默认无用户配置时仍构建 3 个数据中心。
- `build_storages(config: dict)` 支持任意数量储能；默认无用户配置时仍构建 1 个储能。

- [ ] **Step 1: 写失败测试**：提交两个自定义数据中心和两个储能，验证 ID、母线和资源参数独立保留；验证非法母线和非法 SOC 被拒绝。
- [ ] **Step 2: 运行测试确认失败**：`pytest tests/loaders/test_user_resources.py -q`。
- [ ] **Step 3: 实现用户列表构建和拓扑母线引用校验**，保留现有默认模拟配置。
- [ ] **Step 4: 运行测试确认通过**：`pytest tests/loaders/test_user_resources.py -q`。

### Task 4: 仿真引擎和命令行 JSON 入口

**Files:**
- Modify: `src/simulation/engine.py`
- Modify: `src/simulation/orchestrator.py`
- Create: `config/user_config.example.json`
- Create: `tests/simulation/test_user_config_engine.py`

**Interfaces:**
- `SimulationEngine(user_config_file: str | None = None, user_config: dict | None = None, ...)` 支持前端字典和 JSON 文件。
- CLI 新增 `--user-config`，其优先级高于 YAML 和旧的单项 CLI 参数。

- [ ] **Step 1: 写失败测试**：用用户字典初始化引擎，验证自定义 `start_datetime`、优化模式、数据文件路径、数据中心和储能被采用；验证用户拓扑优先。
- [ ] **Step 2: 运行测试确认失败**：`pytest tests/simulation/test_user_config_engine.py -q`。
- [ ] **Step 3: 实现配置合并、路径解析、拓扑注入和资源构建流程**。
- [ ] **Step 4: 编写前端可参考的 `user_config.example.json`**，默认示例为 3 个数据中心和 1 个储能。
- [ ] **Step 5: 运行测试确认通过**：`pytest tests/simulation/test_user_config_engine.py -q`。

### Task 5: 兼容性、文档、备份与全量验证

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-10-05-frontend-json-configuration-design.md`
- Create: `tests/integration/test_json_configuration_compatibility.py`

- [ ] **Step 1: 写兼容性测试**：旧 `platform.yaml`、旧电价 `periods`、旧 CLI 参数和无用户拓扑时的默认 IEEE39 全部可启动。
- [ ] **Step 2: 运行兼容性测试确认失败或暴露回归**：`pytest tests/integration/test_json_configuration_compatibility.py -q`。
- [ ] **Step 3: 更新 README**，说明前端 JSON、拓扑 JSON、上传文件和错误格式。
- [ ] **Step 4: 运行专项测试、编译检查和可用的全量测试**：`pytest -q`、`python -m compileall -q src tests`。
- [ ] **Step 5: 将 `src`、`tests`、`config`、`docs`、`README.md` 和新增示例/拓扑文件同步到 `F:\\cesynergy1`，再用文件哈希确认一致。**

