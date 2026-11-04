# 浅色专业分析风前端仪表盘 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不改变仿真核心逻辑的前提下，将现有前端升级为浅色 16:9 算电协同运行驾驶舱，并增加实时运行总览、资源、任务和告警展示。

**Architecture:** 后端继续通过现有 `/simulation/status` 提供实时状态，仅补充前端展示所需的聚合字段；前端沿用原生 HTML/CSS/JavaScript 和内嵌 SVG，不引入图表依赖。页面分为配置控制、运行总览、监测卡片和底部分析图表四个区域，所有缺失字段均显示明确占位状态。

**Tech Stack:** FastAPI、Python、原生 HTML、CSS、JavaScript、SVG、pytest、Node `--check`。

**Spec:** `docs/superpowers/specs/2026-10-11-light-dashboard-design.md`

## Global Constraints

- 采用 16:9 桌面画布，浅灰白背景、白色信息卡、浅蓝边框和轻阴影。
- 不改变任务调度、优化和电网计算逻辑。
- 图表保持无第三方运行时依赖，使用现有内嵌 SVG 绘制方式。
- 实时统计按当前配置的高频统计间隔更新，前端按约 1 秒轮询状态并按 `second` 去重历史点。
- 所有新增卡片允许缺失数据，不能用随机值或静态示例值覆盖真实结果。
- 导出格式和导出接口保持不变。

## Review Focus

- 后端缺少健康或告警指标时，前端应显示“暂无数据/暂无告警”，不能报错；由任务 1 的状态聚合测试覆盖。
- 数据中心列表动态变化时，资源卡和算力堆叠图应按返回的 ID 工作，不依赖固定三个中心；由任务 2 的渲染数据测试覆盖。
- 同一仿真秒被轮询多次时，历史记录不能重复；由任务 2 的状态合并测试覆盖。
- 没有运行任务或历史为空时，图表应显示零值坐标而不是空白或 NaN；由任务 2 的空数据测试覆盖。
- 视口窄于桌面比例时，页面不能挤压或截断配置控件；由任务 3 的静态 CSS 检查覆盖。

### Task 1: 后端实时展示聚合字段

**Files:**
- Modify: `src/simulation/engine.py`（统计记录和状态聚合）
- Modify: `src/api/frontend_routes.py`（如需暴露额外摘要字段）
- Test: `tests/simulation/test_engine_step.py`、`tests/api/test_status.py`

**Interfaces:**
- Produces: `latest_stats.running_compute_by_datacenter: dict[str, {name: str, compute_tflops: float}]`；可选健康字段缺失时保持现有响应兼容。

- [ ] **Step 1: Write failing tests**：验证运行任务按数据中心汇总算力，空数据中心列表返回空映射，状态响应可安全读取缺失健康字段。
- [ ] **Step 2: Run tests and verify failure**：运行 `pytest tests/simulation/test_engine_step.py tests/api/test_status.py -q`，确认新字段断言失败。
- [ ] **Step 3: Implement minimal aggregation**：在 `SimulationEngine` 统计路径中复用 `dc_sims[*].running_tasks`，按 `required_compute` 求和并写入统计记录；不修改调度和潮流计算。
- [ ] **Step 4: Run focused tests**：确认新增测试和既有状态测试通过。
- [ ] **Step 5: Commit**：`git add src/simulation/engine.py src/api/frontend_routes.py tests/simulation/test_engine_step.py tests/api/test_status.py && git commit -m "feat: expose dashboard runtime aggregates"`

### Task 2: 前端浅色驾驶舱结构与实时卡片

**Files:**
- Modify: `src/web/index.html`
- Modify: `src/web/app.js`
- Modify: `tests/api/test_frontend_static.py`

**Interfaces:**
- Consumes: `/simulation/status` 的 `latest_stats`、`carbon`、`configuration` 和 `optimization` 字段，以及任务算力聚合字段。
- Produces: `mergeHistoryRecord(record)`, `stackedBarChart(target, records)` 和资源/告警卡片的 DOM 更新逻辑。

- [ ] **Step 1: Write failing static tests**：断言页面包含运行总览容器、数据中心资源卡、任务队列卡、实时告警卡、浅色主题标记和导出控件；脚本包含历史去重和堆叠图函数。
- [ ] **Step 2: Run focused static test**：运行 `pytest tests/api/test_frontend_static.py -q`，确认新增标记不存在。
- [ ] **Step 3: Implement page structure**：保留现有上传和仿真控制，加入顶部 KPI、中心算电流向示意、右侧监测卡片和底部四图布局。
- [ ] **Step 4: Implement client rendering**：增加按 `second` 去重的历史合并、动态数据中心资源卡、任务状态卡、无数据/无告警占位，以及堆叠柱状图和实时指标更新。
- [ ] **Step 5: Run Node syntax and focused tests**：运行 `node --check src/web/app.js` 和 `pytest tests/api/test_frontend_static.py -q`。
- [ ] **Step 6: Commit**：`git add src/web/index.html src/web/app.js tests/api/test_frontend_static.py && git commit -m "feat: add light operations cockpit UI"`

### Task 3: 浅色主题与响应式 16:9 样式

**Files:**
- Modify: `src/web/styles.css`
- Modify: `tests/api/test_frontend_static.py`

**Interfaces:**
- Consumes: Task 2 的 DOM 类名和卡片结构。
- Produces: 桌面 16:9 网格布局、浅色主题变量、移动端单列滚动布局和图表视觉样式。

- [ ] **Step 1: Write failing CSS/static assertions**：检查 16:9、浅色背景、白色卡片、响应式断点和资源/告警卡片样式标记。
- [ ] **Step 2: Run test to verify failure**：运行 `pytest tests/api/test_frontend_static.py -q`。
- [ ] **Step 3: Implement CSS**：设置浅灰白画布、深蓝文字、蓝青主色、卡片阴影和 16:9 桌面网格；在窄屏取消固定比例并改为单列滚动。
- [ ] **Step 4: Run focused checks**：确认静态测试、Node 语法检查和页面 HTML 请求通过。
- [ ] **Step 5: Commit**：`git add src/web/styles.css tests/api/test_frontend_static.py && git commit -m "style: apply light responsive dashboard theme"`

### Task 4: 集成验证与回归

**Files:**
- Modify: `README.md`（如需补充新的页面展示说明）
- Test: existing test suite

**Interfaces:**
- Consumes: Tasks 1–3 的后端字段和前端模块。
- Produces: 可启动、可配置、可实时刷新、可导出的完整页面。

- [ ] **Step 1: Run complete test suite**：运行 `pytest -q --disable-warnings`，确认所有测试通过。
- [ ] **Step 2: Run frontend checks**：运行 `node --check src/web/app.js`，并通过 FastAPI `TestClient` 请求 `/` 和 `/static/app.js`。
- [ ] **Step 3: Review responsive and missing-data paths**：确认空统计、动态数据中心、重复秒数据和窄屏布局均有明确行为。
- [ ] **Step 4: Commit integration changes**：`git add . && git commit -m "feat: complete light dashboard refresh"`
