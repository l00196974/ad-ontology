---
name: metric-data-extractor
description: 核心指标数据提取工具，统一查询华为广告数据API，支持语义检索维度值
metadata: {"openclaw": {"requires": {"env": ["HUAWEI_ADS_APP_ID", "HUAWEI_ADS_SECRET"]}, "primaryEnv": "HUAWEI_ADS_SECRET"}}
user-invocable: true
---

# 核心指标数据提取

作为数据分析的"双手"，本 Skill 提供统一的指标查询接口，自动处理实体对齐、语义检索、API 认证和错误纠正。

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
  --metrics "cost,leads" \
  --start-date "2026-01-01" \
  --end-date "2026-01-15" \
  --dimensions "day" \
  --filters '{"推广对象": "元保保险"}'
```

Windows PowerShell（请使用单行命令，避免续行符导致参数解析错误）：

```powershell
query-metrics --metrics "cost,leads" --start-date "2026-01-01" --end-date "2026-01-15" --dimensions "day" --filters '{"推广对象": "元保保险"}'
```

**参数：**

- `--metrics`: 指标列表，逗号分隔（支持中文别名）
- `--start-date`: 开始日期，格式 `YYYY-MM-DD`
- `--end-date`: 结束日期，格式 `YYYY-MM-DD`
- `--dimensions`: 维度列表，逗号分隔，可选
- `--filters`: 过滤条件 JSON，可选
- `--mock`: 使用 Mock 服务，本地调试时启用

### search-dimension-values

语义搜索维度值。

**用法：**

Linux / macOS：

```bash
search-dimension-values --dimension "promotionTarget" --query "保险产品" --top-k 5
```

Windows PowerShell（请使用单行命令，避免续行符导致参数解析错误）：

```powershell
search-dimension-values --dimension "promotionTarget" --query "保险产品" --top-k 5
```

**参数：**

- `--dimension`: 维度编码
- `--query`: 搜索关键词
- `--top-k`: 返回结果数，默认 5

## 配置文件

- `config/metrics.csv`: 指标定义
- `config/dimensions.csv`: 维度定义
- `config/dimension-values.csv`: 维度值库

## 典型流程

1. 使用 `query-metrics` 输入自然语言指标、维度与过滤条件。
2. 工具先执行实体对齐。
3. 如果过滤值无法精确匹配，工具自动尝试 `search-dimension-values` 做语义修复。
4. 组装 DSL 并调用真实 API 或 Mock 服务。
5. 返回结构化 JSON 结果。
