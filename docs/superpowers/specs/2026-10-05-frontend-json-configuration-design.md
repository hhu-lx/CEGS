# 前端 JSON 配置与 JSON 电力拓扑重构设计

## 1. 目标

将用户可配置内容从 `platform.yaml` 中移出，改为由前端提交 JSON 配置和用户上传的数据文件。电力拓扑不再固定使用 `pandapower.networks.case39()`，而是优先从 JSON 拓扑文件构建 Pandapower 网络。

本次重构需要满足：

- 用户不需要编辑 YAML 即可完成一次仿真配置；
- 前端提交的配置可以直接创建 `SimulationEngine`；
- 电价、优化模式、目标函数参数、仿真参数、数据中心和储能均可由 JSON 配置；
- 负荷、光伏、风电、基础发电和任务数据继续通过上传文件提供；
- 拓扑文件采用 JSON 格式，可描述节点、线路、变压器、负荷、发电机、新能源和储能；
- 保留当前命令行和旧 YAML 的兼容路径，避免已有实验无法运行。

默认模拟数据规模保持现有设置：3 个数据中心和 1 个储能设备。该默认规模只用于示例和无用户配置时的演示，不限制前端 JSON 后续提交更多数据中心或储能设备。

## 2. 配置分层

### 2.1 系统默认配置

YAML 只保存后端默认值和内部参数，不作为用户编辑入口，主要包括：

- 默认数据目录和报告目录；
- COPT 运行环境和许可证相关路径；
- 系统安全上限；
- 默认拓扑文件；
- 默认目标函数和默认仿真参数。

### 2.2 用户仿真配置

新增用户配置加载器，支持从 `user_config.json` 或前端传入的 Python 字典加载。用户配置分为：

```json
{
  "simulation": {},
  "optimization": {},
  "pricing": {},
  "data_sources": {},
  "data_centers": [],
  "storages": [],
  "topology": {}
}
```

配置优先级为：

```text
前端 JSON > 命令行参数 > 系统默认配置
```

配置加载后必须先进行结构和取值校验，再创建仿真引擎。

## 3. 用户 JSON 结构

### 3.1 仿真参数

```json
"simulation": {
  "start_datetime": "2026-10-05T00:00:00",
  "duration_hours": 24,
  "step_seconds": 1,
  "stats_interval_seconds": 300,
  "time_scale": 1.0,
  "grid_time_compression": 1.0,
  "task_time_compression": 0.003
}
```

### 3.2 优化参数

```json
"optimization": {
  "mode": "none",
  "objective": "min_cost",
  "objective_function": null,
  "weights": {
    "cost": 1.0,
    "carbon": 1.0,
    "delay": 0.0
  }
}
```

`mode` 支持：

- `none`：固定峰谷电价和规则调度；
- `hierarchical`：先分配任务，再进行能源优化；
- `joint`：任务分配和能源调度联合优化。

### 3.3 电价参数

前端可以直接提交时段，也可以提交电价文件引用：

```json
"pricing": {
  "mode": "fixed_tou",
  "periods": [
    {"start_hour": 0, "end_hour": 7, "price": 0.30, "label": "valley"},
    {"start_hour": 7, "end_hour": 17, "price": 0.60, "label": "flat"},
    {"start_hour": 17, "end_hour": 21, "price": 1.00, "label": "peak"},
    {"start_hour": 21, "end_hour": 24, "price": 0.30, "label": "valley"}
  ],
  "file": null
}
```

固定电价必须覆盖完整的 `0–24` 小时，时段不能重叠或留空；单位为元/kWh。

### 3.4 数据文件

```json
"data_sources": {
  "topology_file": "uploads/topology.json",
  "load_file": "uploads/load.csv",
  "pv_file": "uploads/pv.csv",
  "wind_file": "uploads/wind.csv",
  "base_generation_file": "uploads/base_generation_pu.csv",
  "task_file": "uploads/tasks.csv"
}
```

路径由后端进行安全解析，只允许访问配置的上传目录、项目数据目录或明确的用户工作目录，禁止通过 `..` 越权访问。

### 3.5 数据中心参数

数据中心采用用户 JSON 中的列表定义，不再固定使用 YAML 中的 DC1、DC2 和 DC3。用户可以配置数据中心数量、标识、接入母线、算力、带宽、PUE、设备池和设备功率曲线：

```json
"data_centers": [
  {
    "id": "DC-BJ",
    "name": "北京数据中心",
    "region": "north",
    "grid_bus_id": 3,
    "total_compute": 200.0,
    "total_bandwidth": 100000.0,
    "power_per_tflops": 0.5,
    "profit_margin": 1.3,
    "pue": 1.15,
    "device_pool": [
      {
        "model": "GPU-H100",
        "equipment_type": "compute",
        "quantity": 3,
        "compute_tflops": 80.0,
        "rated_power_kw": 0.70,
        "idle_power_kw": 0.35,
        "power_curve_file": "uploads/gpu_h100_curve.csv"
      },
      {
        "model": "Chiller-500kW",
        "equipment_type": "cooling",
        "quantity": 1,
        "rated_power_kw": 220.0,
        "idle_power_kw": 35.0,
        "power_curve_file": "uploads/chiller_curve.csv"
      }
    ]
  }
]
```

校验要求包括：数据中心 ID 唯一、`grid_bus_id` 必须存在、算力和带宽不能为负、PUE 必须大于等于 1、设备数量和额定功率不能为负。任务表中的 `user_specified_data_center` 为空时，由调度器从该列表中分配；不为空时必须引用一个已配置的数据中心 ID。

## 4. JSON 电力拓扑

新增拓扑加载器和拓扑构建器。拓扑 JSON 采用与 Pandapower 解耦的中立格式：

```json
{
  "name": "IEEE39",
  "base_mva": 100.0,
  "buses": [
    {"id": 1, "name": "Bus 1", "vn_kv": 345.0, "type": "PQ"}
  ],
  "lines": [
    {
      "from_bus": 1,
      "to_bus": 2,
      "length_km": 1.0,
      "r_ohm_per_km": 0.01,
      "x_ohm_per_km": 0.1,
      "c_nf_per_km": 10.0,
      "max_i_ka": 1.0
    }
  ],
  "transformers": [],
  "loads": [],
  "generators": [],
  "renewables": [],
  "storages": []
}
```

拓扑构建器负责：

- 创建 bus、line、transformer、load 和 generator；
- 建立节点编号到 Pandapower 索引的映射；
- 校验所有引用的节点存在；
- 校验电压等级、容量和线路参数为合法数值；
- 将光伏、风电和储能接入节点；
- 保留 IEEE39 JSON 模板作为默认拓扑。

当用户未提交拓扑文件时，系统使用默认拓扑；提交后优先使用用户拓扑。

储能采用设备列表建模，不限制为单个储能或单个节点。每个储能设备通过 `bus_id` 接入已有母线，同一母线可以挂接多个储能设备；如果用户希望增加新的储能接入位置，应在拓扑 JSON 的 `buses` 中先定义该母线，再在 `storages` 中引用它。示例：

```json
"storages": [
  {
    "id": "storage-1",
    "bus_id": 10,
    "capacity_mwh": 100.0,
    "max_power_mw": 25.0,
    "initial_soc_mwh": 50.0,
    "min_soc_mwh": 10.0,
    "charge_efficiency": 0.95,
    "discharge_efficiency": 0.95
  },
  {
    "id": "storage-2",
    "bus_id": 20,
    "capacity_mwh": 60.0,
    "max_power_mw": 15.0,
    "initial_soc_mwh": 30.0,
    "min_soc_mwh": 6.0,
    "charge_efficiency": 0.95,
    "discharge_efficiency": 0.95
  }
]
```

储能校验包括：`bus_id` 必须存在、容量和功率不能为负、初始 SOC 必须位于最低 SOC 与容量之间、效率必须位于 `0–1` 之间。优化器将每个储能设备作为独立资源，同时满足各设备的 SOC、充放电功率和效率约束。

## 5. 仿真引擎接口

`SimulationEngine` 新增用户配置入口：

```python
SimulationEngine(
    config_file=None,
    user_config_file=None,
    user_config=None,
    ...
)
```

前端服务使用 `user_config` 字典；命令行使用 `--user-config path/to/user_config.json`。旧的 `config_file`、`--load`、`--pv`、`--wind` 参数继续兼容，但优先级低于用户 JSON。

## 6. 错误处理

用户配置错误必须在仿真启动前返回可读错误，不允许运行到中途才失败。错误至少包含：

- 字段路径，例如 `pricing.periods[2].price`；
- 错误原因；
- 合法范围或示例值。

典型错误包括：拓扑节点不存在、时段重叠、电价覆盖不完整、优化模式非法、数据文件不存在、时序长度不一致和路径越权。

## 7. 兼容与迁移

- 保留 `platform.yaml` 作为默认配置和旧实验入口；
- 旧的 `electricity_pricing.periods` 继续支持；
- 旧的 IEEE39 默认网络继续支持，但内部改由默认 JSON 拓扑生成；
- 现有输出 CSV、SVG 和任务生命周期不改变；
- 现有三种优化模式和用户目标函数接口不改变。

## 8. 测试要求

新增测试覆盖：

- 用户 JSON 加载和默认值合并；
- JSON Schema/字段校验；
- 电价时段从 JSON 和文件加载；
- 拓扑 JSON 的 bus、line、generator 构建；
- 拓扑节点引用错误；
- 用户拓扑优先于默认拓扑；
- 路径越权拒绝；
- `SimulationEngine(user_config=...)` 能够完成初始化；
- 旧 YAML 和命令行入口回归测试。

## 9. 实施边界

本阶段实现后端配置和拓扑输入接口，不直接实现完整前端页面。前端只需按照本规范提交 JSON 和上传文件即可接入；后续可以在此接口之上增加 Web API 和表单页面。
