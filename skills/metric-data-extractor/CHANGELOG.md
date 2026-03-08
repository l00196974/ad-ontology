# 数据配置和Mock服务优化说明

## 更新概览

基于华为广告本体模型文档,对 metric-data-extractor skill 的内置数据和 mock 服务进行了全面优化。

## 更新内容

### 1. 维度配置 (dimensions.csv)

扩展到 **26个维度**,覆盖:
- 基础维度: 日期、推广对象、渠道、设备等
- 广告投放: 广告主、计划、任务、媒体、版位等
- 用户属性: 年龄、性别、地域、场景等
- 汽车行业: 汽车品牌、车型等
- 内容相关: 内容类型、搜索意图等
- 时间维度: 时段、星期等

### 2. 指标配置 (metrics.csv)

扩展到 **27个指标**,包括:

#### 核心指标
- cost (消耗)
- leads (线索量)
- impressions (展现量)
- clicks (点击量)
- conversions (转化量)

#### 计算指标
- ctr (点击率)
- cvr (转化率)
- cpc (点击成本)
- cpm (千次展现成本)
- cpa (转化成本)
- roi (投资回报率)

#### 广告请求相关
- requests (广告请求量)
- fills (广告填充量)
- fillRate (填充率)

#### APP相关
- downloads (下载量)
- installs (安装量)
- activations (激活量)

#### 其他转化
- registrations (注册量)
- purchases (购买量)
- revenue (收入)

#### 落地页指标
- avgDuration (平均停留时长)
- bounceRate (跳出率)

#### 深浅层转化
- deepConversions (深度转化量)
- shallowConversions (浅层转化量)

#### 视频指标
- videoViews (视频播放量)
- videoCompletions (视频完播量)
- videoCompletionRate (视频完播率)

### 3. 维度值数据 (dimension-values.csv)

扩充到 **85个维度值**,包括:
- 推广对象: 元保保险、问界M7/M9、比亚迪汉/唐等
- 渠道: 信息流、搜索、开屏、横幅、插屏
- 设备: Android、iOS、HarmonyOS
- 媒体: 华为浏览器、视频、音乐、应用市场、新闻
- 汽车品牌: 问界、比亚迪、特斯拉、理想
- 汽车车型: M7、M9、汉、唐、Model Y
- 地域: 北京、上海、广东、全国
- 年龄段: 18-24、25-34、35-44、45+
- 性别: 男、女、未知
- 以及其他各维度的枚举值

每个维度值包含:
- value_code: 值代码
- value_name: 值名称
- value_aliases: 别名(用于语义搜索)
- value_desc: 值描述

### 4. Mock服务优化 (mock/mock-server.js)

#### 新增功能
1. **支持所有27个指标**: 每个指标都有合理的基准值和随机波动
2. **支持所有26个维度**: 每个维度都有完整的枚举值列表
3. **智能数据生成**:
   - 比率类指标(ctr, cvr等)保持在0-1之间
   - 成本类指标有±10%的随机波动
   - 数量类指标有±15%的随机波动
   - 时长类指标符合实际场景
4. **多维度交叉**: 支持任意维度组合查询
5. **过滤条件**: 支持按维度值过滤数据

#### 数据特性
- 所有数据包含随机波动,模拟真实场景
- 比率指标自动约束在合理范围
- 支持日期范围查询
- 支持多维度分组

### 5. 测试场景 (mock/mock-data.json)

新增 **10个预定义测试场景**:
1. default-cost-trend: 默认消耗趋势
2. multi-metric-by-channel: 多指标按渠道分组
3. car-model-performance: 汽车车型推广效果
4. device-analysis: 设备维度分析
5. region-cost-comparison: 地域消耗对比
6. conversion-funnel: 转化漏斗分析
7. video-ad-performance: 视频广告效果
8. age-gender-targeting: 年龄性别定向分析
9. media-position-analysis: 媒体版位分析
10. roi-analysis: ROI投资回报分析

### 6. 文档和测试

#### 新增文档
- `mock/README.md`: Mock服务完整使用说明
  - 支持的维度和指标列表
  - 请求示例
  - 数据特性说明
  - 环境变量配置

#### 新增测试脚本
- `mock/test-mock.sh`: 自动化测试脚本
  - 6个典型场景的测试用例
  - 覆盖单维度、多维度、过滤条件等场景

## 使用方式

### 启动Mock服务
```bash
cd skills/metric-data-extractor
node mock/mock-server.js
```

### 运行测试
```bash
cd skills/metric-data-extractor
./mock/test-mock.sh
```

### 查询示例
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
      "end": "2026-01-07"
    }]
  }'
```

## 数据完整性

所有配置文件都是基于华为广告本体模型文档生成的基础版本,你可以在此基础上:
1. 补充更多维度值到 dimension-values.csv
2. 调整指标的支持维度列表
3. 添加更多使用限制说明
4. 扩展mock服务的数据生成逻辑

## 下一步建议

1. **补充维度值**: 根据实际业务需求,在 dimension-values.csv 中添加更多真实的维度值
2. **调整指标关系**: 在 metrics.csv 中完善每个指标支持的维度列表
3. **优化Mock数据**: 根据真实数据分布,调整 mock-server.js 中的基准值和波动范围
4. **添加验证规则**: 在配置文件中添加数据验证规则,如取值范围、必填项等
5. **集成真实API**: 将mock服务切换为真实API的代理模式,支持开发/测试环境切换

## 文件清单

```
skills/metric-data-extractor/
├── config/
│   ├── dimensions.csv          (26个维度)
│   ├── metrics.csv             (27个指标)
│   └── dimension-values.csv    (85个维度值)
├── mock/
│   ├── mock-server.js          (优化的mock服务)
│   ├── mock-data.json          (10个测试场景)
│   ├── README.md               (使用文档)
│   └── test-mock.sh            (测试脚本)
└── ...
```

## 兼容性说明

所有更新都向后兼容,不影响现有代码:
- CSV文件格式保持不变
- Mock服务API接口保持不变
- 只是扩展了支持的维度和指标范围
