---
name: data-insight-visualizer
description: 对结构化广告数据做基础指标加工，并输出可渲染的 ECharts 配置。
allowed-tools:
  - Bash
  - Read
  - Grep
  - Glob
---

# data-insight-visualizer

## 适用场景

这个 Skill 用于承接已经拿到的 JSON 数据结果，完成两类动作：

1. 指标加工：计算同比、环比、占比、TGI。
2. 图表渲染：把结构化数据转成 ECharts option JSON。

## 输入约定

推荐把上游数据整理成 JSON，再交给本 Skill：

- `data`：数组，每一项是一行数据。
- `metricKey`：需要计算的指标字段名，例如 `cost`、`clicks`。
- `dimensionKey`：维度字段名，默认可用 `date`、`channel`、`name`。
- `operation`：支持 `yoy`、`mom`、`ratio`、`tgi`。

## 指标计算

### 1. 计算同比

```json
{
  "operation": "yoy",
  "metricKey": "cost",
  "dimensionKey": "date",
  "data": [
    { "date": "2025-01-01", "cost": 100 },
    { "date": "2026-01-01", "cost": 120 }
  ]
}
```

返回结果会补充：

- `currentValue`
- `previousValue`
- `change`
- `changeRate`
- `comparisonKey`

### 2. 计算环比

`mom` 与 `yoy` 类似，但按上一个月同一天进行比对。

### 3. 计算占比

```json
{
  "operation": "ratio",
  "metricKey": "cost",
  "dimensionKey": "channel",
  "data": [
    { "channel": "A", "cost": 40 },
    { "channel": "B", "cost": 60 }
  ]
}
```

返回中会补充：

- `total`
- `ratio`
- `percentage`

### 4. 计算 TGI

```json
{
  "operation": "tgi",
  "targetMetricKey": "targetConversions",
  "targetBaseKey": "targetUsers",
  "overallMetricKey": "overallConversions",
  "overallBaseKey": "overallUsers",
  "dimensionKey": "segment",
  "data": [
    {
      "segment": "年轻用户",
      "targetConversions": 30,
      "targetUsers": 100,
      "overallConversions": 20,
      "overallUsers": 100
    }
  ]
}
```

TGI 公式：

`(targetMetric / targetBase) / (overallMetric / overallBase) * 100`

## 图表渲染

支持以下图表类型：

- `line`
- `bar`
- `pie`
- `scatter`

推荐输入：

```json
{
  "chartType": "line",
  "title": "消耗趋势",
  "dimensionKey": "date",
  "series": [
    {
      "name": "消耗",
      "metricKey": "cost",
      "data": [
        { "date": "2026-01-01", "cost": 100 },
        { "date": "2026-01-02", "cost": 120 }
      ]
    }
  ]
}
```

## CLI 用法

### calculate-metrics

可从标准输入读取。

Linux / macOS：

```bash
cat input.json | node ./bin/calculate-metrics.js
```

Windows PowerShell：

```powershell
Get-Content .\input.json | node .\bin\calculate-metrics.js
```

也可指定文件。

Linux / macOS：

```bash
node ./bin/calculate-metrics.js --input ./input.json
```

Windows PowerShell：

```powershell
node .\bin\calculate-metrics.js --input .\input.json
```

### render-echarts

Linux / macOS：

```bash
cat chart-input.json | node ./bin/render-echarts.js
```

Windows PowerShell：

```powershell
Get-Content .\chart-input.json | node .\bin\render-echarts.js
```

## 错误输出

两个 CLI 都会在失败时输出结构化 JSON：

```json
{
  "error": {
    "code": "INVALID_INPUT",
    "message": "operation is required"
  }
}
```

## 设计原则

- 行为确定性，不依赖外部服务。
- 输入尽量简单，方便上游 Skill 串联。
- 输出纯 JSON，方便前端和 Agent 后续处理。
