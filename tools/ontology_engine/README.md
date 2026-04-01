# 双螺旋确权系统

基于现网行为数据的用户购车意图确权与营销策略生成系统。

输入用户原始行为日志（搜索/浏览/导航/广告点击），通过 CEP 规则 + Need 圈选规则 + LLM 双螺旋确权，输出每个用户的主导购车 Need 及归一化强度分，供营销策略层消费。

---

## 环境准备

```bash
cd tools/ontology_engine

python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

依赖：`networkx` / `anthropic` / `openai`（LLM 调用可选）

LLM 配置（可选，不配置则走内置规则 fallback）：

```bash
cp scripts/llm_config.json.example scripts/llm_config.json
# 编辑 llm_config.json，填入 api_key / model / base_url
```

---

## 快速运行

所有命令均在 `tools/ontology_engine/` 目录下执行。

```bash
# 无数据文件 — 自动生成 500+500 条模拟数据，验证全流程
python3 scripts/poc_dual_spiral.py

# 使用真实数据
python3 scripts/poc_dual_spiral.py \
  --positive data/positive.json \
  --negative data/negative.json

# 持久化到本地数据库（下次跳过导入，直接复用）
python3 scripts/poc_dual_spiral.py \
  --positive data/positive.json \
  --negative data/negative.json \
  --db data/cache.db

# 重置数据库重跑
python3 scripts/poc_dual_spiral.py --db data/cache.db --reset \
  --positive data/positive.json --negative data/negative.json
```

### 分阶段运行

```bash
# 只跑数据加载
python3 scripts/poc_dual_spiral.py --positive data/positive.json --stop-after load

# 跑到 CEP 衍生事件
python3 scripts/poc_dual_spiral.py --positive data/positive.json --stop-after cep

# 跑到人群分层
python3 scripts/poc_dual_spiral.py --positive data/positive.json --stop-after segment

# 跑到 TBOX 图谱初始化
python3 scripts/poc_dual_spiral.py --positive data/positive.json --stop-after tbox
```

### 人工规则模式（推荐生产用）

```bash
# 指定 CEP 规则文件，跳过 LLM CEP 推导
python3 scripts/poc_dual_spiral.py \
  --positive data/positive.json \
  --cep-rules data/cep_rules.action.json

# 指定 Need 圈选规则，跳过 LLM 多轮假设
python3 scripts/poc_dual_spiral.py \
  --positive data/positive.json \
  --cep-rules data/cep_rules.action.json \
  --need-rules data/need_rules.template.json

# 启用品牌竞争力模型
python3 scripts/poc_dual_spiral.py \
  --positive data/positive.json \
  --cep-rules data/cep_rules.action.json \
  --need-rules data/need_rules.template.json \
  --brand 比亚迪
```

### 参数覆盖

```bash
# CLI 参数覆盖
python3 scripts/poc_dual_spiral.py \
  --tgi-threshold 130 \
  --max-rounds 5 \
  --min-confirmed 4 \
  --positive data/positive.json

# 环境变量覆盖（优先级低于 CLI 参数）
TGI_THRESHOLD=130 MAX_ROUNDS=5 python3 scripts/poc_dual_spiral.py ...
```

完整参数列表：

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--positive` | — | 正样本 JSON（有留资行为） |
| `--negative` | — | 负样本 JSON（无留资行为） |
| `--db` | `:memory:` | SQLite 缓存路径，指定后持久化 |
| `--reset` | false | 重置数据库 |
| `--cep-rules` | — | CEP 规则 JSON 文件（跳过 LLM CEP） |
| `--need-rules` | — | Need 圈选规则 JSON 文件（跳过 LLM 假设） |
| `--brand` | — | 广告主品牌，启用竞争力系数 |
| `--tgi-threshold` | 120 | TGI 确权阈值 |
| `--max-rounds` | 10 | LLM 最大推理轮数 |
| `--min-confirmed` | 30 | 最低确权假设数 |
| `--interactive` | false | 关键步骤暂停确认 |
| `--stop-after` | — | 提前退出：load/cep/segment/tbox/hypothesis |
| `--dump-unknown` | false | 打印无法识别的 res_key |

---

## 人工规则导入工具

`rule_import.py` 独立于主流程，用于增量维护 CEP 规则和 Need 圈选规则。

```bash
# 导入 CEP 规则 → user_derived_events
python3 scripts/rule_import.py \
  --db data/cache.db \
  --cep-rules data/cep_rules.action.json

# 导入 Need 圈选规则 → user_need_segments
python3 scripts/rule_import.py \
  --db data/cache.db \
  --need-rules data/need_rules.template.json

# 仅验证语法，不写入数据库
python3 scripts/rule_import.py \
  --db data/cache.db \
  --cep-rules data/cep_rules.action.json \
  --dry-run

# 强制覆盖已存在的同名规则
python3 scripts/rule_import.py \
  --db data/cache.db \
  --need-rules data/need_rules.template.json \
  --force

# 自定义 TGI 告警阈值（不影响导入，仅控制 ⚠ 提示）
python3 scripts/rule_import.py \
  --db data/cache.db \
  --cep-rules data/cep_rules.action.json \
  --tgi-threshold 130
```

导入逻辑：
- 语法不合法 → 拒绝，打印原因
- 命中用户数 < `--min-users`（默认10）→ 拒绝
- TGI 低于阈值 → 仅警告，不拒绝
- 同名规则已存在 → 默认跳过，`--force` 覆盖

---

## 数据流水线

```
原始数据（JSON）
  ├─ user_tag  → user_profile（用户画像，14个字段）
  └─ res_key   → user_raw_events（原始行为，17种 event_type）
                        ↓
               CEP 规则（raw.* 表达式）
                        ↓
          user_derived_events（衍生事件 / Action_*）
                        ↓
          Need 圈选规则（event.* / profile.* 表达式）
                        ↓
          user_need_segments（Need 圈选人群）
                        ↓
          Need 强度打分（满足度 × 时间衰减 × IDF → Softmax）
                        ↓
          user_need_scores（归一化强度分 + 主导 Need 标记）
                        ↓
                  策略生成
```

两条路径均最终写入 `user_need_scores`：

| 路径 | 触发条件 | 打分函数 |
|---|---|---|
| **规则路径** | 指定 `--need-rules` | `compute_need_scores_from_rules` |
| **图谱路径** | LLM 多轮假设确权后 | `compute_need_scores`（含品牌竞争力模型） |

---

## Need 强度打分模型

```
raw_score(user, need) = Fulfillment × TimeDecay × Specificity
```

### 层1：行为满足度（Fulfillment）

解析 Need 规则引用的 Action 事件，按命中次数与饱和阈值比较：

```
contribution(action) = min(命中次数 / saturation, 1.0)
Fulfillment = mean(contribution) over all referenced Actions
```

`saturation` 在 `data/cep_rules.action.json` 中每条规则单独配置：

| Action | saturation | 含义 |
|---|---|---|
| `Action_Book_Car_Test_Drive` | 1 | 试驾1次即满分 |
| `Action_Calculate_Car_Loan` | 2 | 看车贷/落地价2次饱和 |
| `Action_Browse_Car_Detail_Freq` | 5 | 持续浏览详情需5次 |
| `Action_Browse_Car_News_Gen` | 8 | 泛资讯低强度行为需8次 |

### 层2：时间衰减（TimeDecay）

取该 Need 所有 Action 中最近一次命中时间：

```
TimeDecay = e^{-λ × days_since}，λ = ln2 / halflife_days（默认半衰期7天）
```

| 距今天数 | TimeDecay |
|---|---|
| 1天 | 0.91 |
| 7天 | 0.50 |
| 14天 | 0.25 |
| 30天 | 0.05 |

### 层3：稀缺性（Specificity / IDF）

覆盖用户越少的 Need，本底分越高：

```
Specificity = log(N_total / N_need_users)
```

| 示例 Need | 覆盖人群 | IDF（万级用户基准） |
|---|---|---|
| 性价比/折扣（大众诉求） | ~80% | 0.22 |
| 智驾科技偏好 | ~12% | 2.12 |
| 越野性能诉求（小众） | ~3% | 3.51 |

### 归一化（Softmax）

对每个用户的所有 Need 做 Softmax，`dominant_flag=1` 标记主导 Need。

---

## 数据库表结构

### `user_profile`

```sql
CREATE TABLE user_profile (
    user_id        TEXT PRIMARY KEY,
    gender         TEXT,   -- 男性 / 女性
    age_group      TEXT,   -- 18-24岁 / 24-34岁 / 35-44岁 / 45-54岁
    city           TEXT,
    city_tier      TEXT,   -- 一线 / 新一线 / 二线 / 三线
    house_status   TEXT,   -- 有房产 / 无房产
    car_status     TEXT,   -- 有车 / 无车
    marital_status TEXT,
    child_status   TEXT,
    consume_freq   TEXT,
    device_price   TEXT,
    is_lead        INTEGER -- 1=正样本 0=负样本
);
```

### `user_raw_events`

```sql
CREATE TABLE user_raw_events (
    event_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    TEXT,
    event_time TEXT,   -- YYYYMMDDHH
    time_str   TEXT,   -- YYYYMMDD
    dur_time   REAL,   -- 停留秒数
    event_type TEXT,
    attr_json  TEXT    -- JSON，各类型字段见下表
);
```

| event_type | 中文含义 | attr_json 字段 |
|---|---|---|
| `search_vertical` | 搜索三车垂媒 | `brand`、`channel` |
| `search_general` | 搜索泛资讯 | `brand` |
| `search_entertainment` | 搜索泛娱乐种草 | `brand`、`model` |
| `view_car_detail` | 浏览车辆详情页 | `brand`、`model` |
| `view_car_compare` | 浏览车型对比页 | `brand` |
| `view_loan_calc` | 浏览车贷计算页 | `brand`、`model` |
| `view_short_video` | 浏览短视频 | `brand` |
| `view_contact_sales` | 浏览联系销售页 | `brand` |
| `view_floor_price` | 浏览查落地价页 | `brand` |
| `test_drive` | 试驾 | `model` |
| `order_placed` | 大定（正式下单） | `model` |
| `ad_click` | 广告点击 | `app`、`category`、`brand`、`creative` |
| `pass_dealership` | 路过门店 | _(空)_ |
| `map_app_use` | 地图/打车软件使用 | _(空)_ |
| `rental_app_use` | 租车软件使用 | _(空)_ |
| `lead_submit` | 留资 | `channel`（**正样本标志，规则中禁止引用**） |
| `unknown` | 无法识别 | `raw` |

### `user_derived_events`

```sql
CREATE TABLE user_derived_events (
    event_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id            TEXT,
    event_time         TEXT,
    derived_event_type TEXT,   -- Action_* 或内置 CEP 名称
    source_rule        TEXT,
    attr_json          TEXT
);
```

### `user_need_segments`

```sql
CREATE TABLE user_need_segments (
    need_name  TEXT NOT NULL,
    user_id    TEXT NOT NULL,
    rule_expr  TEXT,
    derived_at TEXT,
    PRIMARY KEY (need_name, user_id)
);
```

### `user_need_scores`

```sql
CREATE TABLE user_need_scores (
    user_id          TEXT,
    need_name        TEXT,
    raw_score        REAL,    -- Fulfillment × TimeDecay × Specificity
    normalized_score REAL,    -- Softmax 归一化（0~1）
    dominant_flag    INTEGER, -- 1=该用户主导 Need
    fulfillment      REAL,    -- 行为满足度（0~1）
    time_decay       REAL,    -- 时间衰减系数（0~1）
    specificity      REAL,    -- IDF 稀缺性分值
    computed_at      TEXT
);
```

---

## 规则表达式语法

CEP 规则和 Need 规则统一使用声明式表达式，不写 SQL。

### CEP 规则（`raw.*`，作用于 `user_raw_events`）

```
# 存在性 / 计数 / 时长
raw.search_vertical.exists
raw.search_vertical.count >= 3
raw.view_car_detail.days >= 2          # 跨越不同日期数
raw.search_general.dur_max >= 3000     # 最大单次停留秒数

# 属性过滤
raw.search_vertical[brand!=null].count >= 2
raw.view_car_detail[brand].distinct >= 3   # 不同品牌数

# 关键词匹配（attr_json 全文 LIKE）
raw.search_general.contains("续航")
raw.search_vertical.contains("NOA")

# 时序（A 必须早于 B）
raw.search_vertical.before.view_car_detail.exists

# 跨事件同属性（同品牌详情+车贷）
raw.view_car_detail[brand].same.raw.view_loan_calc[brand].exists

# 逻辑组合
raw.search_vertical.count >= 3 AND raw.view_car_detail.exists
raw.test_drive.exists OR raw.view_contact_sales.exists
NOT (raw.search_vertical.exists OR raw.view_car_detail.exists)
```

### Need 圈选规则（`event.*` / `profile.*`）

```
# 衍生事件（user_derived_events）
event.Action_Calculate_Car_Loan.exists
event.Action_Browse_Car_Detail_Freq.count >= 1

# 用户画像（user_profile）
profile.city_tier IN ['一线', '新一线']
profile.age_group = '35-44岁'
profile.car_status != '有车'

# 组合
event.Action_Search_Car_EV_Range.exists AND event.Action_Calculate_Car_Loan.exists
event.Action_Book_Car_Test_Drive.exists AND profile.city_tier IN ['一线', '新一线']
event.Action_Browse_Luxury_Car_Brand.exists AND NOT event.Action_Search_Car_Discount.exists
```

---

## 配置文件

| 文件 | 说明 |
|---|---|
| `data/cep_rules.action.json` | 18条 Action_* 衍生事件规则（含 `saturation` 饱和阈值） |
| `data/cep_rules.example.json` | 7条基础 CEP 规则示例 |
| `data/need_rules.template.json` | 30条 Need 圈选规则模板（4大分组，含 `item_tags`） |
| `data/need_rules.example.json` | 5条 Need 规则示例 |
| `scripts/llm_config.json` | LLM 连接配置（api_key / model / base_url） |

### `cep_rules.action.json` 格式

```json
[
  {
    "name": "Action_Book_Car_Test_Drive",
    "desc": "预约汽车试驾或联系汽车销售",
    "rule": "raw.test_drive.exists OR raw.view_contact_sales.exists",
    "saturation": 1,
    "note": "试驾/联系销售是强意向信号，1次即饱和"
  }
]
```

### `need_rules.template.json` 格式

```json
[
  {
    "need_name": "Need_Advanced_Auto_Driving",
    "description": "高阶自动驾驶与前沿科技尝鲜诉求",
    "rule": "event.Action_Search_Car_ADAS_Tech.exists AND event.Action_Browse_Car_Detail_Freq.exists",
    "weight": 0.9,
    "item_tags": "城市NOA, 激光雷达"
  }
]
```

---

## 脚本模块

| 模块 | 职责 |
|---|---|
| `poc_dual_spiral.py` | 主入口，串联完整七步流程 |
| `config.py` | 全局配置常量，支持环境变量和 CLI 参数覆盖 |
| `data_loader.py` | 解析 user_tag / res_key，写入 user_profile + user_raw_events |
| `analytics.py` | CEP 执行、TGI 计算、因果检验、Need 强度打分（规则路径 + 图谱路径） |
| `rule_expr.py` | 规则表达式解析器与执行器（tokenizer + 递归下降 parser + executor） |
| `rule_import.py` | 独立规则导入工具，增量维护 CEP 规则和 Need 圈选规则 |
| `ontology.py` | 图谱节点/边管理、序列化、LLM prompt 上下文生成 |
| `llm_client.py` | LLM 调用封装，推导 CEP 规则 / Need / Item / Media |
| `hypothesis.py` | Hypothesis 数据类，多轮假设生成与 TGI 验证 |
| `strategy.py` | 营销策略生成（Item ← Need ← Event ← User 链路） |

---

## 目录结构

```
tools/ontology_engine/
├── scripts/
│   ├── poc_dual_spiral.py     # 主入口
│   ├── rule_import.py         # 独立规则导入工具
│   ├── rule_expr.py           # 规则表达式引擎
│   ├── analytics.py           # 分析层（TGI / CEP / 打分）
│   ├── config.py              # 配置层
│   ├── data_loader.py         # 数据加载层
│   ├── ontology.py            # 图谱层
│   ├── llm_client.py          # LLM 调用层
│   ├── hypothesis.py          # 假设层
│   ├── strategy.py            # 策略层
│   └── llm_config.json.example
│
└── data/
    ├── cep_rules.action.json   # 18条 Action_* CEP 规则（含 saturation）
    ├── cep_rules.example.json  # 基础 CEP 示例
    ├── need_rules.template.json # 30条 Need 圈选规则模板
    └── need_rules.example.json  # Need 规则示例
```
