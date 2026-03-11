---
name: data-insight-visualizer
description: 对结构化广告数据做基础指标加工。专注于数据计算，不包含图表渲染功能。
---

## 工具列表

### calculate-metrics
计算指标的同比、环比、占比、TGI等。

**参数：**

- `--input`: 输入JSON文件路径，可选，如果不提供则从stdin读取

**输入JSON格式：**
```json
{
  "operation": "yoy|mom|ratio|tgi",
  "metricKey": "cost",
  "dimensionKey": "date",
  "data": [...]
}
```

**示例：**
```bash
echo '{"operation":"ratio","metricKey":"cost","dimensionKey":"channel","data":[...]}' | node bin/calculate-metrics.js
```

---

# data-insight-visualizer

## 适用场景

这个 Skill 用于承接已经拿到的 JSON 数据结果，完成指标加工：

1. 指标加工：计算同比、环比、占比、TGI。

**注意：图表渲染功能已移除，LLM 应直接生成 ECharts 配置。**

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

## 错误输出

CLI 会在失败时输出结构化 JSON：

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
- 专注于数据计算，不包含图表渲染。
- 输入尽量简单，方便上游 Skill 串联。
- 输出纯 JSON，方便前端和 Agent 后续处理。
