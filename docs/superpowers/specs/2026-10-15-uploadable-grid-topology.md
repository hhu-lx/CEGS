# 可上传电力拓扑设计

用户可在前端上传 JSON 电力拓扑；未上传时继续使用内置 IEEE39。专用拓扑上传优先于平台默认值，用户通用配置仍不得内嵌拓扑。

上传文件沿用现有 `buses`、`lines`、`transformers`、`loads`、`external_grids`、`generators`、`renewables`、`storages` 结构，并可增加：

```json
"resource_mapping": {
  "pv_bus": 10,
  "wind_bus": 20,
  "load_buses": [1, 2, 3]
}
```

应用配置时校验拓扑结构、pandapower 网络可构建性、资源映射节点，以及有效数据中心和储能的接入节点。校验成功后通过 `ui_config.topology` 传给仿真引擎，不依赖上传临时文件。前端显示文件名、拓扑名称、母线数、线路数和校验状态。

提供一份与默认数据中心节点 3、16、21，光伏节点 10、风电节点 20 兼容的测试 JSON 文件。
