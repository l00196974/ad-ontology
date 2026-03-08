# Mock 服务使用说明

## 概述

Mock 服务模拟华为广告数据 API,支持所有维度和指标的查询测试。

## 启动服务

```bash
cd skills/metric-data-extractor
node mock/mock-server.js
```

默认端口: 3000 (可通过环境变量 PORT 修改)

## 支持的维度

| 维度代码 | 维度名称 | 示例值 |
|---------|---------|--------|
| day | 日期 | 2026-01-01 |
| promotionTarget | 推广对象 | yuanbao_insurance, wenjie_m7, byd_han |
| channel | 渠道 | feed, search, splash, banner |
| device | 设备 | android, ios, harmony |
| media | 媒体 | huawei_browser, huawei_video |
| mediaPosition | 媒体版位 | feed_position, search_position |
| industry | 行业 | automotive, insurance, ecommerce |
| conversionGoal | 转化目标 | download, install, register, lead |
| bidStrategy | 出价策略 | cpc, cpm, cpa, ocpc |
| region | 地域 | beijing, shanghai, guangdong |
| age | 年龄 | 18-24, 25-34, 35-44, 45+ |
| gender | 性别 | male, female, unknown |
| carBrand | 汽车品牌 | wenjie, byd, tesla, lixiang |
| carModel | 汽车车型 | m7, m9, han, tang, model_y |
| contentType | 内容类型 | auto_news, auto_review, auto_price |
| searchIntent | 搜索意图 | brand_search, price_search |
| userScenario | 用户场景 | commute, shopping, work |
| timeSlot | 时段 | morning, noon, evening, night |
| weekday | 星期 | monday, tuesday, ... sunday |

## 支持的指标

### 核心指标
- **cost**: 消耗金额
- **leads**: 线索量
- **impressions**: 展现量
- **clicks**: 点击量
- **conversions**: 转化量

### 计算指标
- **ctr**: 点击率
- **cvr**: 转化率
- **cpc**: 点击成本
- **cpm**: 千次展现成本
- **cpa**: 转化成本
- **roi**: 投资回报率

### 广告请求相关
- **requests**: 广告请求量
- **fills**: 广告填充量
- **fillRate**: 填充率

### APP相关
- **downloads**: 下载量
- **installs**: 安装量
- **activations**: 激活量

### 其他转化
- **registrations**: 注册量
- **purchases**: 购买量
- **revenue**: 收入

### 落地页指标
- **avgDuration**: 平均停留时长(秒)
- **bounceRate**: 跳出率

### 深浅层转化
- **deepConversions**: 深度转化量
- **shallowConversions**: 浅层转化量

### 视频指标
- **videoViews**: 视频播放量
- **videoCompletions**: 视频完播量
- **videoCompletionRate**: 视频完播率

## 请求示例

### 基础查询
```bash
curl -X POST http://localhost:3000/ads-data/openapi/v1/chart/common \
  -H "Content-Type: application/json" \
  -d '{
    "indicators": [{"indicatorKey": "cost"}],
    "dimensions": ["day"],
    "dateTimeFilter": [{
      "start": "2026-01-01",
      "end": "2026-01-07"
    }]
  }'
```

### 多维度查询
```bash
curl -X POST http://localhost:3000/ads-data/openapi/v1/chart/common \
  -H "Content-Type: application/json" \
  -d '{
    "indicators": [
      {"indicatorKey": "cost"},
      {"indicatorKey": "leads"},
      {"indicatorKey": "cpa"}
    ],
    "dimensions": ["day", "channel"],
    "dateTimeFilter": [{
      "start": "2026-01-01",
      "end": "2026-01-05"
    }]
  }'
```

### 带过滤条件查询
```bash
curl -X POST http://localhost:3000/ads-data/openapi/v1/chart/common \
  -H "Content-Type: application/json" \
  -d '{
    "indicators": [
      {"indicatorKey": "impressions"},
      {"indicatorKey": "clicks"},
      {"indicatorKey": "ctr"}
    ],
    "dimensions": ["device"],
    "filterConditions": [{
      "oper": "EQUAL",
      "source": "promotionTarget",
      "targetValue": ["wenjie_m7"]
    }],
    "dateTimeFilter": [{
      "start": "2026-01-01",
      "end": "2026-01-10"
    }]
  }'
```

## 数据特性

1. **随机波动**: 所有指标值都包含随机波动,模拟真实数据
2. **比率约束**: 比率类指标(ctr, cvr等)保持在0-1之间
3. **维度组合**: 支持多维度交叉查询
4. **过滤支持**: 支持按维度值过滤数据

## 测试场景

mock-data.json 文件包含10个预定义测试场景:

1. **default-cost-trend**: 默认消耗趋势
2. **multi-metric-by-channel**: 多指标按渠道分组
3. **car-model-performance**: 汽车车型推广效果
4. **device-analysis**: 设备维度分析
5. **region-cost-comparison**: 地域消耗对比
6. **conversion-funnel**: 转化漏斗分析
7. **video-ad-performance**: 视频广告效果
8. **age-gender-targeting**: 年龄性别定向分析
9. **media-position-analysis**: 媒体版位分析
10. **roi-analysis**: ROI投资回报分析

## 配置文件说明

### dimensions.csv
定义所有支持的维度及其描述和示例值。

### metrics.csv
定义所有支持的指标,包括:
- 指标代码和名称
- 指标描述
- 支持的维度列表
- 使用限制说明

### dimension-values.csv
定义每个维度的具体枚举值,包括:
- 维度代码
- 值代码
- 值名称
- 别名(用于语义搜索)
- 值描述

## 环境变量

```bash
# 修改端口
PORT=8080 node mock/mock-server.js
```

## 注意事项

1. Mock 服务不需要认证,直接调用即可
2. 返回数据格式与真实 API 完全一致
3. 数据为随机生成,每次请求结果会有差异
4. 建议在开发和测试环境使用
