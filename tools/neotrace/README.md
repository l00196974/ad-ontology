# NEOTrace

汽车广告精准投放工具，从原始用户行为/画像数据出发，经 CEP 规则挖掘验证、广告本体构建，到生成完整投放策略的离线+在线系统。

## 核心思路

```
原始行为/画像数据
      ↓
LLM 挖掘 CEP 行为规则 → TGI 验证 → 人工审核发布
      ↓
广告本体构建（Item / Media / Creative）
      ↓
策略查询：Item + 预算 → LLM 推断目标特征 → CEP 规则圈人 → 投放策略
```

**设计原则**：不设 NEED 中间层。Item 通过 LLM 直接映射到目标行为/画像特征，CEP 规则直接圈出用户，NEED 标签仅作为策略输出的解释性描述，不存入本体。

---

## 目录结构

```
neotrace/
├── neotrace/
│   ├── storage/          # 存储抽象层
│   │   ├── base.py           # StorageAdapter 抽象接口
│   │   └── duckdb_adapter.py # DuckDB 实现（三层数据架构）
│   ├── ingest/
│   │   └── loader.py         # 原始数据加载（支持合并格式 / 独立格式）
│   ├── mining/
│   │   ├── stats.py          # 数据分布统计（DataProfiler）
│   │   ├── cep_miner.py      # LLM 挖掘 CEP 行为规则
│   │   └── rule_store.py     # 规则审核发布（draft → published）
│   ├── ontology/
│   │   ├── tbox/             # 本体 Schema（Item / Media / Creative）
│   │   └── abox/             # 本体实例加载
│   ├── strategy/
│   │   └── engine.py         # 策略引擎（核心查询入口）
│   └── spark/
│       └── generator.py      # PySpark 打标作业生成
├── scripts/
│   └── offline_pipeline.py   # 离线 Pipeline 主入口
├── data/                     # 示例数据
└── tests/                    # 单元 + 集成测试
```

---

## 快速开始

### 1. 安装依赖

```bash
cd tools/neotrace
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

### 2. 配置 LLM

复制 `.env.example` 为 `.env`，填入火山引擎（或其他 OpenAI 兼容接口）配置：

```bash
export LLM_BASE_URL="https://ark.cn-beijing.volces.com/api/coding/v3"
export LLM_API_KEY="your-api-key"
export LLM_MODEL="ark-code-latest"
```

### 3. 运行离线 Pipeline

```bash
python scripts/offline_pipeline.py \
    --profiles  data/mengshi_profiles.txt \
    --behaviors data/mengshi_behaviors.txt \
    --cep-rules 5 \
    --auto-publish \
    --min-tgi-cep 100 \
    --media-config data/mengshi_media.json \
    --db output/my.duckdb
```

Pipeline 执行步骤：
1. 加载原始数据（画像 + 行为）→ DuckDB
2. 统计数据分布，生成报告
3. LLM 挖掘 CEP 行为规则，计算 TGI
4. 人工审核（或 `--auto-publish` 自动发布达标规则）
5. 构建广告本体（TBox + ABox）
6. 生成 PySpark 打标作业

### 4. 策略查询

```python
from neotrace.storage.duckdb_adapter import DuckDBAdapter
from neotrace.strategy.engine import StrategyEngine
from neotrace.ontology.tbox.tbox_builder import build_tbox
from neotrace.ontology.abox.abox_loader import load_abox

storage = DuckDBAdapter("output/my.duckdb")
build_tbox()
load_abox(storage, item_config_path="data/mengshi_media.json")

engine = StrategyEngine(storage)
result = engine.query("东风猛士917", budget=500000)

print(result.summary)
# 建议将 50万 预算投放给 25 位高意向用户，主要覆盖 户外越野需求、高端品质需求、里程焦虑缓解
# 等需求人群，核心圈人规则：猛士车型精准搜索规则、线下门店到访规则，
# 推荐媒体：华为智能短信(智能短信-视频卡片)、华为智能短信(智能短信-图文卡片)，
# 参考平均 TGI=144，预估转化 21 人。
```

---

## 数据格式

### 画像文件（每行一个 JSON）

支持两种格式：

**合并格式**（画像 + 行为同一行，推荐）：
```json
{
  "user_id": "u001",
  "user_tag": "年龄段:35-44岁#性别:男性#购车:有车#户外出行倾向:高",
  "is_converted": 1,
  "user_events": [
    {"event": "搜索_三车垂媒_东风-猛士917{{ }}", "event_time": "2026-01-05 10:00:00"},
    {"event": "留资_线下渠道", "event_time": "2026-02-20 10:00:00"}
  ]
}
```

**独立格式**：
```json
{"user_id": "u001", "age_range": "35-44岁", "gender": "男性", "is_converted": 1}
```

`is_converted` 可不填，加载器会自动从 `user_events` 中推断（含 `留资_` 事件则为 1）。

### 行为文件（每行一个 JSON）

```json
{"user_id": "u001", "event": "搜索_三车垂媒_东风-猛士917{{ }}", "event_time": "2026-01-05 10:00:00"}
```

### 媒体配置文件（JSON 数组）

```json
[
  {
    "placement_id": "sms_huawei_001",
    "platform_name": "华为智能短信",
    "ad_format": "智能短信",
    "buying_type": "CPM",
    "creative_specs": ["文字140字以内", "带落地页链接"]
  }
]
```

---

## 核心概念

### CEP 规则（行为清洗规则）

将原始零散行为抽象为高语义事件，由 LLM 基于数据分布推荐，经 TGI 验证后发布。

| 字段 | 说明 |
|------|------|
| `name` | 规则名称（中文） |
| `event_type` | 产出的语义事件类型（英文下划线） |
| `conditions` | 匹配条件列表 |
| `tgi` | TGI 值（命中用户转化率 / 全局转化率 × 100） |
| `support` | 覆盖率（命中用户数 / 总用户数） |
| `status` | draft → published / rejected |

### TGI（Target Group Index）

```
TGI = (命中用户留资率 / 全样本留资率) × 100
```

TGI > 100 表示命中用户转化率高于基准，值越高规则质量越好。

### 策略引擎流程

```
query(item_name, budget)
  ├─ 从本体读取 Item 属性（车型/价格/动力/座位等）
  ├─ LLM 推断目标人群特征 + 已发布 CEP 规则相关度权重
  ├─ 按规则权重在 raw_profiles/raw_behaviors 匹配用户，计算意向分
  ├─ TopK 用户（预算约束：budget / 人均 CPM 成本）
  ├─ 媒体推荐（基于主导需求标签关键词匹配）
  ├─ 素材推荐（从本体 Creative 实例匹配）
  └─ 输出 StrategyResult（含推导需求标签作解释）
```

---

## Pipeline 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--profiles` | 必填 | 画像 txt 文件路径 |
| `--behaviors` | 必填 | 行为 txt 文件路径 |
| `--db` | `neotrace.duckdb` | DuckDB 数据库路径 |
| `--cep-rules` | 10 | LLM 生成 CEP 规则数量 |
| `--auto-publish` | False | 自动发布达标规则（不交互） |
| `--min-tgi-cep` | 100.0 | CEP 自动发布 TGI 阈值 |
| `--media-config` | None | 媒体广告位配置 JSON |
| `--output-dir` | `output` | 输出目录 |
| `--skip-steps` | 空 | 跳过步骤（如 `1,2`） |

---

## 运行测试

```bash
python -m pytest tests/ -v
```

---

## 示例数据

`data/` 目录下提供东风猛士917场景的示例数据：

- `mengshi_profiles.txt` — 25个用户画像（15正样本 + 10负样本）
- `mengshi_behaviors.txt` — 105条行为记录
- `mengshi_media.json` — 华为智能短信三种广告位配置
