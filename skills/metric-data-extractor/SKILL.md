---
name: metric-data-extractor
description: 核心指标数据提取工具，统一查询华为广告数据API，支持语义检索维度值
metadata: {}
user-invocable: true
---

# 核心指标数据提取

作为数据分析的"双手"，本 Skill 提供统一的指标查询接口，自动处理实体对齐、语义检索、API 认证和错误纠正。

## 🚨 重要：LLM使用指南

### 数据查询工作流程（必须遵循）

**当用户提出数据查询需求时，必须按以下顺序执行：**

1. **了解系统能力** - 首先调用 `list_metrics` 和 `list_dimensions`
2. **展示系统能力** - 向用户展示支持的指标和维度
3. **确认维度值** - 使用 `search_dimension_values` 确认具体的维度值
4. **执行查询** - 调用 `query_metrics` 进行数据查询

### 关键规则

**必须使用英文代码：**
- ✅ 指标：`click,receivedExposure,actualSpent`
- ❌ 错误：`点击量,实收曝光次数,结算点击流水`
- ✅ 维度：`promotionTarget,reqDay,mediaName`
- ❌ 错误：`推广标的,请求时间,媒体名称`
- ✅ 过滤：`{"promotionTarget": ["问界M7"]}`
- ❌ 错误：`{"推广标的": ["问界M7"]}`

**常见错误代码对照：**
- ❌ `clicks` → ✅ `click`
- ❌ `impressions` → ✅ `receivedExposure`
- ❌ `conversion_cost` → ✅ `realityConversionCost`
- ❌ `product_name` → ✅ `promotionTarget`
- ❌ `day` → ✅ `reqDay`

**Mock数据时间范围：** 2026-03-01 到 2026-03-07（使用 config.json 配置本地服务地址时生效）
- 支持的推广对象：问界M7、元保保险、某电商APP、某教育APP

## 使用场景

- 查询广告消耗、线索量、展现量、点击量等核心指标
- 按时间、渠道、推广对象、创意等维度拆解数据
- 支持自然语言参数，自动映射到 API 字段
- 当维度值不匹配时，自动语义搜索相似值

## 工具

### query-metrics

查询华为广告指标数据。

**用法：**

Linux / macOS：

```bash
query-metrics \
  --metrics "click,receivedExposure,actualSpent" \
  --start-date "2026-01-01" \
  --end-date "2026-01-15" \
  --dimensions "reqDay,promotionTarget" \
  --filters '{"promotionTarget": ["问界M7"]}'
```

Windows PowerShell（请使用单行命令，避免续行符导致参数解析错误）：

```powershell
query-metrics --metrics "click,receivedExposure,actualSpent" --start-date "2026-01-01" --end-date "2026-01-15" --dimensions "reqDay,promotionTarget" --filters '{"promotionTarget": ["问界M7"]}'
```

**查询示例：**

1. **基础效果查询（问界M7点击和曝光）：**
```bash
query-metrics --metrics "click,receivedExposure" --start-date "2026-03-01" --end-date "2026-03-07" --dimensions "reqDay" --filters '{"promotionTarget": ["问界M7"]}'
```

2. **成本分析查询：**
```bash
query-metrics --metrics "actualSpent,clickActualSpent,realityConversionCost" --start-date "2026-03-01" --end-date "2026-03-07" --dimensions "reqDay" --filters '{"promotionTarget": ["问界M7"]}'
```

3. **转化效果查询：**
```bash
query-metrics --metrics "adGroupShallowConversionNumber,adGroupDeepConversionNumber,pbiConvertRate" --start-date "2026-03-01" --end-date "2026-03-07" --dimensions "reqDay" --filters '{"promotionTarget": ["问界M7"]}'
```

4. **媒体对比查询：**
```bash
query-metrics --metrics "click,receivedExposure" --start-date "2026-03-01" --end-date "2026-03-05" --dimensions "mediaName"
```

**参数：**

- `--metrics`: 指标列表，逗号分隔（**必须使用英文指标代码，不要使用中文名称**）
- `--start-date`: 开始日期，格式 `YYYY-MM-DD`
- `--end-date`: 结束日期，格式 `YYYY-MM-DD`
- `--dimensions`: 维度列表，逗号分隔，可选（**必须使用英文维度代码**）
- `--filters`: 过滤条件 JSON，可选

**常用指标英文代码对照表：**

| 中文名称 | 英文代码 | 说明 |
|---------|---------|------|
| 点击量 | `click` | 基础点击指标 |
| 实收曝光次数 | `receivedExposure` | 曝光量指标 |
| 结算点击流水 | `actualSpent` | 成本指标 |
| 实收点击流水 | `clickActualSpent` | 成本指标 |
| 任务浅层转化数 | `adGroupShallowConversionNumber` | 转化指标 |
| 任务深层转化数 | `adGroupDeepConversionNumber` | 转化指标 |
| 转化率 | `pbiConvertRate` | 转化率指标 |
| 实际转化成本 | `realityConversionCost` | 成本指标 |

**常用维度英文代码对照表：**

| 中文名称 | 英文代码 | 说明 |
|---------|---------|------|
| 请求时间 | `reqDay` | 按天分组 |
| 推广标的 | `promotionTarget` | 推广对象 |
| 媒体名称 | `mediaName` | 媒体渠道 |
| 计费方式 | `priceType` | 计费类型 |
| 任务名称 | `adGroupName` | 广告任务 |

### search-dimension-values

语义搜索维度值。

**🚨 重要：使用搜索结果时，必须使用 `value` 字段而不是 `value_desc` 字段进行后续查询！**

**用法：**

Linux / macOS：

```bash
search-dimension-values --dimension "promotionTarget" --query "保险产品" --top-k 5
```

Windows PowerShell（请使用单行命令，避免续行符导致参数解析错误）：

```powershell
search-dimension-values --dimension "promotionTarget" --query "保险产品" --top-k 5
```

**返回格式示例：**
```json
{
  "dimension": "promotionTarget",
  "query": "问界",
  "results": [
    {
      "value": "问界M7",           // ← 用这个值进行查询！
      "value_desc": "问界M7车型",  // ← 不要用这个描述！
      "similarity": 1
    }
  ]
}
```

**🚨 关键规则：**
- ✅ 正确：使用 `value` 字段 → `{"promotionTarget": ["问界M7"]}`
- ❌ 错误：使用 `value_desc` 字段 → `{"promotionTarget": ["问界M7车型"]}`

**参数：**

- `--dimension`: 维度编码（必须使用从 list_dimensions 获取的准确代码）
- `--query`: 搜索关键词
- `--top-k`: 返回结果数，默认 5

### list-metrics

列出所有可用的指标。

**用法：**

```bash
list-metrics --format json
```

**参数：**

- `--format`: 输出格式，json（Agent系统用）或table（命令行用），默认table   table格式会节省token,建议优先使用

**输出：**

返回JSON格式的指标列表，包含指标代码、名称和描述。

### list-dimensions

列出所有可用的维度。

**用法：**

```bash
list-dimensions --format json
```

**参数：**

- `--format`: 输出格式，json（Agent系统用）或table（命令行用），默认table

**输出：**

返回JSON格式的维度列表，包含维度代码、名称和描述。

## 配置文件

- `config/metrics.csv`: 指标定义
- `config/dimensions.csv`: 维度定义
- `config/dimension-values.csv`: 维度值库

## 典型流程

1. 使用 `query-metrics` 输入自然语言指标、维度与过滤条件。
2. 工具先执行实体对齐。
3. 如果过滤值无法精确匹配，工具自动尝试 `search-dimension-values` 做语义修复。
4. 组装 DSL 并根据 config.json 配置调用 API 服务。
5. 返回 ECharts dataset 格式的结构化 JSON 结果。
