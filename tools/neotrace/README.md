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

### 3. 导入数据

**单文件模式**（数据含 `is_converted` 字段或 `user_events` 里有 `留资_` 开头的事件，自动推断正负样本）：

```bash
python scripts/load_data.py \
    --input data/users.txt \
    --db    output/my.duckdb
```

**正负样本双文件模式**（两个文件分别存放转化用户和未转化用户，无需在文件中写 `is_converted`）：

```bash
python scripts/load_data.py \
    --pos  data/positive.txt \
    --neg  data/negative.txt \
    --db   output/my.duckdb
```

两种模式均支持 `--val-ratio`（默认 0.2），导入时自动按 80%/20% 分层抽样划分训练集和验证集，保证正负比例在两个 split 中一致：

```bash
python scripts/load_data.py \
    --pos data/positive.txt \
    --neg data/negative.txt \
    --db  output/my.duckdb \
    --val-ratio 0.2
```

导入完成后会打印训练/验证集的用户数和正样本率，确认分布正常再执行规则挖掘。

> **重复导入说明**：`raw_profiles` 按 `user_id` 主键覆盖，但 `raw_behaviors` 会追加。
> 如需重新导入，加 `--overwrite` 参数先清空两张表再写入：
> ```bash
> python scripts/load_data.py --pos ... --neg ... --db output/my.duckdb --overwrite
> ```

### 4. 挖掘 CEP 规则（交互选择入库）

```bash
python scripts/mine_rules.py \
    --db      output/my.duckdb \
    --n-rules 5
```

挖掘完成后逐条展示规则的训练集/验证集 TGI、覆盖率、稳定性，输入 `y` 发布入库，`n` 跳过，`q` 退出。

TGI 高低不作为过滤条件，所有规则均展示——TGI 作为元数据供后续策略引擎 LLM 推断目标人群时参考。
可通过 `--min-support` 过滤掉覆盖率过低（人群规模不足）的规则：

```bash
python scripts/mine_rules.py \
    --db          output/my.duckdb \
    --n-rules     5 \
    --min-support 0.01   # 至少覆盖 1% 用户，否则圈不到足够人群
```

### 5. 策略查询

```bash
python scripts/query_strategy.py \
    --item   "东风猛士917" \
    --budget 500000 \
    --db     output/my.duckdb
```

可选参数：

| 参数 | 说明 |
|------|------|
| `--media-config` | 媒体广告位配置 JSON（可选，不填则使用规则回退） |
| `--objective` | 优化目标：`conversions`（默认）/ `reach` / `clicks` |

示例输出：
```
  目标人群:
    规模:     12,000 人
    意向分:   P90=2.500  P50=1.000
    参考 TGI: 162
    需求标签: 户外越野需求 / 里程焦虑

  推荐媒体:
    · 华为智能短信 — 智能短信-视频卡片 (CPM)  预算 25.0万  预估触达 6,667人
    ...

  效果预估:
    预估触达: 12,000 人
    预估转化: 240 人
```

---

## 数据格式

### 用户数据文件（每行一个 JSON，合并格式）

画像和行为写在同一行，`user_events` 里的 `res_key` 字段即原始行为：

```json
{
  "user_id": "e2cd256670977755...",
  "user_tag": "年龄段:24-34岁#性别:男性#房产:有房产#购车:未知#城市:武汉市#户外出行倾向:低",
  "user_events": [
    {"timestamp": "2025120516", "res_key": "搜索_三车垂媒_林肯{{ }}", "time_str": "20251205", "dur_time": 0},
    {"timestamp": "2026030404", "res_key": "留资_线下渠道", "time_str": "20260304", "dur_time": 2229.18}
  ]
}
```

`is_converted` 可不填，加载器自动从 `user_events` 推断（含 `留资_` 开头的事件则为已转化）。

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
