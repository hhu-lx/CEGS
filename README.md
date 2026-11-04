# 算电协同平台

这是一个配置驱动的算电协同仿真平台：任务经过数据中心调度后形成计算负荷，负荷进入 Pandapower 电网，储能在节点上进行充放电，真实 COPT 负责任务分配或全局经济—碳排优化。

## 运行环境

需要 Python 3.10+、Pandapower、SimPy、FastAPI 和已授权的 COPT 8（`F:\copt\copt80`）。运行前保留本机 COPT 的环境变量和许可证目录。依赖声明在 [pyproject.toml](../pyproject.toml) 中。

## 数据表

`config/reference/equipment_power_curves.csv` 是可复用的设备功率曲线表，包含 GPU、冷机、UPS 和网络交换机在 0/50/100% 利用率下的代表性功率。启动时由 `reference_tables.equipment_power_curves` 加载；可替换为实测 CSV，字段保持 `model,equipment_type,utilization,power_kw`。

任务数据默认读取 `config/task_data_completed.csv`。该表保留原始任务列，并追加 `task_id`、`data_size_gb`、`required_cpu_cores`、`required_gpu_count`、`required_gpu_type` 和 `user_specified_data_center`。最后一列可以为空；为空时由调度中心/COPT 分配，填写数据中心 ID 时则固定到该中心。原始 `data_updated.xlsx` 不会被覆盖。

如需从新的原始表重新生成覆盖表：

```powershell
F:\python\python.exe -m scripts.generate_task_table --source config/data_updated.xlsx --output config/task_data_completed.csv
```

## 三种运行模式

- `optimization.mode: none`（前端“启发式”）：任务按 FCFS、资源可行性和负载均衡分配，不读取电价、碳强度或电网状态；电力侧仍滚动优化常规机组、风光和储能，并进行 AC 潮流校验。因此它是“不进行算电协同”的对照组，不是“不优化电力”。
- `optimization.mode: hierarchical`（前端“局部优化”）：以页面所选调度策略产生首轮任务选址，随后交替求解任务子问题和电力子问题，最多 5 轮；目标相对变化不超过 `1e-3` 或选址连续两轮不变时停止。后续轮不可行会保留上一严格可行点。
- `optimization.mode: joint`（前端“全局优化”）：任务选址、启动时段、常规机组、风光和储能均在同一个 COPT 模型中求解；独立调度策略由联合模型接管。

三种模式均采用未来 24 小时、1 小时粒度的滚动电力窗口，秒级仿真只执行第一段控制。短于 24 点的预测会循环补齐，并在结果中标记 `forecast_fill: cyclic`。每次电力决策都需通过 AC 潮流校验；失败结果不会标记为严格可行，并会恢复最近一次严格可行运行点。

前端必须先选择优化模型，再选择该模式允许的策略与目标。启发式固定为非协同负载均衡且不提供时延目标；局部优化允许最低价格、低碳、低时延、负载均衡和自定义调度；全局优化的调度由联合模型接管。定价策略在三种模式下均可选择。

### 前端 JSON 配置

前端不需要修改 `platform.yaml`。可以提交 `config/user_config.example.json` 格式的 JSON，或通过命令行传入：

```powershell
F:\python\python.exe main.py --cli --user-config config/user_config.example.json
```

命令行 `--user-config` 仍兼容旧的用户配置格式。Web 前端上传的用户配置则只用于仿真参数、优化目标/权重、数据中心和储能；`config/platform.yaml` 提供其他未覆盖项的默认值。`data_centers` 和 `storages` 上传后分别整体替换平台清单，对象型设置按字段覆盖。

Web 用户配置文件只允许 `simulation`、`optimization`、`data_centers`、`storages` 四个顶层字段。任务文件、峰谷电价 CSV 和电力拓扑 JSON 必须分别通过页面的专用上传控件提交；没有上传任务或拓扑时，分别使用 `platform.yaml` 中的默认任务表和内置 IEEE39。电网时序与设备参考曲线继续由 `platform.yaml` 管理。请从 `config/user_config.example.json` 复制用户配置模板；旧 Web 配置中的 `data_sources`、`tasks`、`pricing`、`electricity_pricing` 或 `topology` 会收到迁移提示，需要移除这些重复来源字段。

自定义拓扑可参考 `config/examples/custom_topology_test.json`。其中 `resource_mapping.pv_bus`、`wind_bus` 和 `load_buses` 指定时序数据的接入节点；拓扑的 `base_mva` 会作为本次仿真的基准容量。页面应用配置时会同时检查线路/设备引用、风光与负荷节点、数据中心节点和储能节点，并尝试构建 pandapower 网络。测试文件与默认数据中心节点 3、16、21 及储能节点 10 兼容，可直接上传。

应用配置后，页面顶部更新总算力规模，运行总览中的数据中心名称也按最终配置显示。上传配置仍按相同的合并规则生效；页面不再单独展示数据中心配置清单。

旧配置中的 `local`、`global` 仍分别兼容为 `hierarchical`、`joint`。

目标可选 `min_cost`、`min_carbon`、`min_curtailment`、`peak_shaving`、`min_delay`、`weighted` 或前端自定义权重。启发式不允许 `min_delay`，其自定义时延权重也必须为 0。

用户拓扑中的常规机组可填写 `generator_type`、`ramp_up_mw_per_hour`、`ramp_down_mw_per_hour`、`cost_linear_yuan_per_mwh`、`cost_quadratic_yuan_per_mw2h` 和 `emission_tco2_per_mwh`。缺失爬坡参数默认采用 `0.5 × max_p_mw / h`；成本与排放从 `coal`、`gas`、`hydro`、`nuclear` 或 `generic_thermal` 平台表补齐。规范化后的 `parameter_sources` 明确记录每个值来自用户还是哪一行默认表；非数值、NaN、无穷值和倒置的出力上下限会被拒绝。

设备功率优先使用 `config/reference/equipment_power_timeseries.csv` 中的一秒级 240 秒周期。每个设备有自己的变化趋势，周期结束后按 `elapsed_seconds % 240` 循环读取，不同设备不会共用 GPU 的抖动曲线。测试时序将单设备参考功率统一放大 100 倍，用于代表参与电网级协同的设备集群。计算设备功率按任务所需设备数量累计；制冷、UPS 和网络功率按任务算力占数据中心总算力的比例分摊。优化器使用完整周期的平均功率；实时仿真每秒重新读取当前周期位置的功率、更新瞬时负荷并积分电能，但不会因此每秒重复执行交流潮流。设备缺少时序数据时回退到功率曲线，数据中心没有设备池时才回退到线性系数。

目标函数可在 YAML 中修改 `objective`，也可以通过 `objective_function: module:function` 加载用户自己的 Python 目标函数（签名为 `(task, data_center, context) -> 数值`）。电价和目标函数均无需修改仿真代码。仿真统计同时提供可配置起始时间对应的 `clock_time`。

前端选择“自定义”调度策略后，可设置电价、负载、碳强度和网络时延权重，或上传 `config/examples/custom_dispatch_strategy.yaml`。选择“自定义”电价策略后，可设置基础电价、本地负荷/算力负荷系数、电压偏差系数和价格上下限，或上传 `config/examples/custom_pricing_strategy.yaml`。两种自定义都是参数化配置，不会执行上传的 Python 代码。

电网时序默认从原始数据的第 16 小时开始：`grid.time_series_start_offset_seconds: 57600` 会同时作用于负荷、光伏、风电和基础发电，避免破坏四类曲线的时间对应关系。该起点仍有光伏出力，并覆盖储能低谷充电和随后晚高峰放电。`base_generation_pu_second.csv` 是不分机组的常规电源基准计划，只随基础负荷变化，不预先扣除风光，也不包含后续到达的算力负荷；运行时按各机组基准容量形成参考出力，再由优化器统一调节。风电和光伏 CSV 按容量系数解释，分别乘以 `grid.wind_capacity_mw` 和 `grid.pv_capacity_mw` 得到可用功率；电网约束下的实际并网功率与可用功率之差才计为弃风弃光。默认装机容量均为 1300 MW，使高出力时段能够出现真实的线路约束和弃电，而低出力时段仍优先全额消纳。

储能不再按固定小时机械充放电。控制器使用实时净负荷（负荷与算力用电减去风光出力）和平滑基准判断峰谷：启发式模式按偏差响应，局部与联合模式通过 COPT 同时约束充电、放电、SOC 和充放电互斥。前端“自定义目标”可直接设置或上传 `config/examples/custom_optimization_objective.yaml`，控制成本、碳排、时延、削峰填谷、弃风弃光和储能损耗权重；上传的目标函数只接受 JSON/YAML 参数，不执行 Python 代码。

任务表中的 `start_time`、`submitted_at`、`duration_seconds` 和 `max_wait_seconds` 均使用秒；不存在单独的释放时间字段。任务按数据文件中的原始时间运行，不再使用任务时间压缩。

仿真每个统计周期会覆盖更新四张独立图片：`reports/grid_power.svg`（负荷/发电）、`reports/task_statistics.svg`（提交/调度/完成）、`reports/task_duration.svg`（计划/实际时长）和 `reports/compute_power.svg`（算力映射功率）；同时生成 `simulation_stats.csv` 和 `task_execution.csv` 明细。统计周期由 `simulation.stats_interval_seconds` 控制，默认 300 秒（5 分钟）；输出目录可通过 `reports.directory` 修改。用浏览器或图片查看器打开 SVG 即可看到最新一帧。

任务状态和日志明确分为四个阶段：`提交`（submitted）、`调度`（scheduling）、`开始`（running）和 `结束`（completed）。任务到达后先进入 `scheduling`，由 `scheduling.batch_interval_seconds` 控制调度批次，默认每 5 秒扫描一次完整队列；`max_tasks_per_batch` 控制单批实际启动的最大任务数。暂时不满足资源条件的任务移到队尾，避免阻塞后续可运行任务。任务统计图和 `task_execution.csv` 会记录调度中状态。

电网负荷、光伏和风电时序支持 `grid.time_compression`，默认 `1.0`，保持原始电网时间尺度；若前期曲线较平滑，这是原始数据在该时间片的真实表现。

内置 IEEE39 拓扑在 `config/topology_ieee39.json` 中将常规机组和平衡节点的电压设定为 1.03 pu，以匹配本平台的 0.95–1.05 pu 运行约束。普通潮流、风光优化后的交流校核与连续潮流均考虑机组无功限值。该设定是仿真工况校准；如果改用自定义拓扑或明显增大数据中心负荷，仍需核对线路额定电流和机组容量，程序不会把实际越限的运行点标记为可行。

## 启动和验证

```powershell
F:\python\python.exe main.py --cli --config config/platform.example.yaml
F:\python\python.exe -m pytest -q --disable-warnings
F:\python\python.exe -m compileall src
```

任务提交接口为 `POST /tasks`；状态接口包括 `/grid/latest`、`/carbon/summary`、`/storage` 和 `/optimization/latest`。

## Web 页面

在 PyCharm 中直接运行项目根目录的 `main.py` 即可启动 Web 服务，默认地址为 `http://127.0.0.1:8000/`。也可以在终端执行：

桌面宽屏下页面内容区域按 16:9 布局，三列面板底部对齐；较小窗口会改为自然滚动和响应式排列。浏览器原生窗口大小由浏览器和操作系统控制。

```powershell
F:\python\python.exe main.py
```

如需保留旧的命令行仿真入口，使用 `F:\python\python.exe main.py --cli`。端口可通过环境变量 `CESYNERGY_PORT` 修改。

启动应用后访问根路径 `/`，即可使用“算电协同仿真平台”页面：

1. 上传任务文件、用户配置 YAML/JSON、峰谷电价 CSV；如需替换内置 IEEE39，再上传电力拓扑 JSON；
2. 选择调度策略、定价策略与启发式/局部/全局优化模型；
3. 点击“应用配置”，校验通过后点击“启动仿真”；
4. 在右侧查看发电、负荷、任务统计和算力功率四张曲线；
5. 点击“结束仿真”后，可导出 JSON、CSV 或 Excel 结果包。导出包含全部统计时刻，并用动态列记录用户自定义的数据中心、机组和储能 ID，不只导出最后一帧。

峰谷电价 CSV 使用字段 `start_hour,end_hour,price`，时段需要覆盖完整 0–24 小时且不能重叠。算力-功率映射由系统预定义为设备功率时序映射，不在页面提交。
