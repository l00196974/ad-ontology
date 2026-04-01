# 汽车营销本体推理引擎

面向汽车营销场景的用户需求推理引擎，基于 OWL 本体 + Python 规则引擎构建。
输入用户画像（城市政策、代际标签、设备档次、看车行为），输出结构化的营销需求标签，供 LLM Agent 直接消费。

---

## 它能做什么

给定一个用户的画像和看车记录，引擎自动推导出他/她的购车核心诉求：

```
用户：张三（北京 · 中坚家庭 · 看了比亚迪汉 + 丰田汉兰达）
        ↓
推导结果：
  [牌照刚需] 绿牌刚需/有桩无畏   ← 北京限牌，且看了纯电车
  [空间刚需] 刚需6至7座          ← 中坚家庭 + 看了大型SUV
  [预算敏感] 预算死锁             ← 中端设备 + 同价位询价2次
```

---

## 快速开始

### 环境准备

```bash
cd tools/ontology_engine

# 创建虚拟环境并安装依赖
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 运行演示脚本（最快上手方式）

```bash
.venv/bin/python scripts/run_demo.py
```

输出包含：5 个示例用户的完整推理结果、JSON 格式输出、购车链路匹配、核心断言验证。

### 运行测试

```bash
.venv/bin/python -m pytest tests/ -v
# 19 passed
```

---

## 核心用法（Python API）

### 三步完成推理

```python
from ontology_engine import build_tbox, load_abox, Reasoner, get_user_needs

# Step 1: 构建 OWL TBox（类定义 + 属性定义）
build_tbox()

# Step 2: 加载 ABox（用户实例 + 车型实例 + 看车关系）
load_abox()

# Step 3: 执行推理规则，将需求标签写回本体
Reasoner().run()

# 查询某用户的推导结果
result = get_user_needs("张三")
for need in result.inferred_needs:
    print(f"[{need.category}] {need.need_label}")
# 输出：
# [牌照刚需] 绿牌刚需/有桩无畏
# [空间刚需] 刚需6至7座
# [预算敏感] 预算死锁
```

### 获取 JSON（供 LLM Function Calling）

```python
from ontology_engine import get_user_needs_json

data = get_user_needs_json("张三")
# 返回完整 dict，字段见下方"返回结构"说明
```

返回结构示例：

```json
{
  "user": "张三",
  "raw_profile": {
    "age_range": "35-44岁",
    "generation_group": "中坚家庭",
    "city_tier": "一线城市",
    "policy_fuel": "燃油车限牌限行",
    "device_price_tier": "中端设备",
    "travel_activity": "高频地图/打车用户",
    "inquiry_frequency": 2,
    "conversion_stage": "留资"
  },
  "interacted_cars": [
    {"name": "比亚迪汉", "power_type": "纯电动", "body_type": "轿车", "car_price_band": "20-30万"},
    {"name": "丰田汉兰达", "power_type": "传统燃油", "body_type": "SUV", "car_price_band": "30-50万"}
  ],
  "inferred_needs": [
    {"need_label": "绿牌刚需/有桩无畏", "need_class": "GreenPlateRequired", "category": "牌照刚需"},
    {"need_label": "刚需6至7座",        "need_class": "SixSevenSeatsRequired", "category": "空间刚需"},
    {"need_label": "预算死锁",           "need_class": "BudgetLocked",          "category": "预算敏感"}
  ],
  "need_count": 3
}
```

### 购车链路匹配

```python
from ontology_engine import get_user_journey

journey = get_user_journey("张三")
print(journey.best_journey_name)   # 家庭扩展型
print(journey.current_stage)       # 留资
print(journey.missing_events)      # ['E003', 'E206', 'E401']  ← 营销介入机会点
print(journey.recommended_cars)    # ['问界M7', '理想L7', '蔚来ES6']
```

---

## GraphDB 模式（生产环境）

数据量上来之后，切换到 GraphDB 后端，获得持久化存储 + SPARQL 复杂查询 + OWL RL 内置推理。

### 启动 GraphDB

```bash
cd docker
docker compose up -d
# 等待约 30 秒，直到 http://localhost:7200 可以访问
```

### 上传本体数据到 GraphDB

```python
from ontology_engine import build_tbox, load_abox, export_and_upload, reset_onto

reset_onto()
build_tbox()
load_abox()

# 首次运行需传入仓库配置文件（自动创建仓库）
export_and_upload(config_ttl_path="docker/graphdb-init/create-repo.ttl")
```

### 用 GraphDB 后端执行推理和查询

```python
from ontology_engine import Reasoner, get_user_needs

# 推理结果写入 GraphDB
Reasoner(backend="graphdb").run()

# 从 GraphDB 查询结果
result = get_user_needs("张三", backend="graphdb")
```

或者设置环境变量，让所有查询默认走 GraphDB：

```bash
export ONTOLOGY_BACKEND=graphdb
export GRAPHDB_URL=http://localhost:7200
export GRAPHDB_REPO=auto-marketing
```

之后直接调用 `get_user_needs("张三")` 无需传 `backend` 参数。

---

## 推理规则说明

引擎内置 4 条规则，按拓扑顺序执行（有依赖关系的规则保证先后顺序）：

| 规则 | rule_id | 触发需求 | 核心条件 |
|------|---------|---------|---------|
| 牌照刚需 | `license_plate_urgency` | 绿牌刚需 / 无桩且限号 / 牌照自由 | 城市限行政策 × 看车动力类型 |
| 空间刚需 | `space_need` | 刚需6至7座 / 单人代步 | 代际标签 × 看车车身/尺寸 |
| 预算敏感 | `budget_sensitivity` | 预算死锁 / 弹性预算 | 询价频次 × 设备档次 × 价格带 |
| 里程焦虑 | `range_mileage_anxiety` | 严重里程焦虑 | 高频出行 × 偏好燃油/增程 × 非绿牌刚需城市（互斥） |

**需求标签全览：**

| 需求标签 | 分类 | OWL 类名 | 触发场景 |
|---------|------|---------|---------|
| 绿牌刚需/有桩无畏 | 牌照刚需 | `GreenPlateRequired` | 限牌/限行城市 + 看了纯电 |
| 无桩且限号 | 牌照刚需 | `NoParkingLimitNumber` | 限牌城市 + 看了插混/增程，但没看纯电 |
| 牌照自由 | 牌照刚需 | `LicenseFree` | 燃油车无限制城市 |
| 刚需6至7座 | 空间刚需 | `SixSevenSeatsRequired` | 中坚家庭/银发群体 + 看 MPV 或大型 SUV |
| 单人代步 | 空间刚需 | `SinglePersonCommute` | 年轻新贵/新锐青年 + 看轿车/小型 SUV |
| 预算死锁 | 预算敏感 | `BudgetLocked` | 同价位询价 ≥ 2 次 + 中低端设备 |
| 弹性预算 | 预算敏感 | `FlexibleBudget` | 跨 ≥ 2 个价格带看车 + 高端/旗舰设备 |
| 严重里程焦虑 | 里程焦虑 | `RangeMileageAnxiety` | 高频出行 + 只看燃油/增程 + 无限制城市 |

---

## 接入真实数据

当前 `load_abox()` 加载的是 `abox/sample_users.py` 中的 5 个示例用户。接入真实用户数据有两种方式：

**方式 A：替换工厂函数**

参考 `abox/sample_users.py` 的写法，写一个从数据库/API 读取真实用户的工厂函数，替换 `abox/abox_loader.py` 中的调用即可。

```python
# abox/abox_loader.py 中替换
from your_data_source import create_user_from_db  # 你的真实数据加载函数

def load_abox():
    initialize_need_singletons()
    # ... 加载车型
    for user_data in fetch_users_from_db():
        create_user_from_db(user_data)   # 写法参考 create_zhangsan()
```

**方式 B：直接 SPARQL UPDATE 写入 GraphDB（推荐大规模）**

启动 GraphDB 后，直接用 SPARQL INSERT 批量写入用户三元组，无需经过 Owlready2。

---

## 目录结构

```
tools/ontology_engine/
├── docker/
│   ├── docker-compose.yml          # GraphDB Free 容器
│   └── graphdb-init/
│       └── create-repo.ttl         # 仓库配置（OWL2 RL 推理器）
│
├── ontology_engine/                # 核心包
│   ├── config/                     # 枚举常量、城市政策、全局配置
│   ├── core/                       # Owlready2 本体单例 + GraphDB 客户端
│   ├── tbox/                       # OWL TBox：类定义 + 属性定义
│   ├── abox/                       # OWL ABox：示例用户/车型 + 导出器
│   ├── rules/                      # 推理规则引擎（4条规则 + 注册表）
│   ├── journey/                    # 事理图谱：35个购车事件 + 链路匹配
│   └── query/                      # Agent 对外接口层（强类型返回值）
│
├── tests/                          # 19 个测试（memory 模式，无需 GraphDB）
├── scripts/
│   └── run_demo.py                 # 完整演示脚本
└── requirements.txt
```

---

## 双螺旋确权系统（scripts/）

基于真实现网数据的用户意图确权与营销策略生成系统，采用 LLM + TGI 双螺旋确权机制。

### 快速运行

```bash
cd tools/ontology_engine

# 无数据文件（自动生成 500+500 条模拟数据）
python3 scripts/poc_dual_spiral.py

# 使用真实数据
python3 scripts/poc_dual_spiral.py \
  --positive data/positive.json \
  --negative data/negative.json

# 指定 CEP 规则文件（跳过 LLM CEP 推导）
python3 scripts/poc_dual_spiral.py \
  --positive data/positive.json \
  --cep-rules data/cep_rules.example.json

# 指定品牌（启用品牌-Need 竞争力模型）
python3 scripts/poc_dual_spiral.py \
  --positive data/positive.json \
  --brand 比亚迪

# 覆盖阈值配置
python3 scripts/poc_dual_spiral.py \
  --tgi-threshold 130 --max-rounds 5 --min-confirmed 4 \
  --positive data/positive.json

# 环境变量方式覆盖
TGI_THRESHOLD=130 MAX_ROUNDS=5 python3 scripts/poc_dual_spiral.py ...
```

### 人工规则导入

```bash
# 导入 CEP 规则（写入 user_derived_events）
python3 scripts/rule_import.py \
  --db data/cache.db \
  --cep-rules data/cep_rules.example.json

# 导入 Need 圈选规则（写入 user_need_segments）
python3 scripts/rule_import.py \
  --db data/cache.db \
  --need-rules data/need_rules.example.json

# 仅验证语法，不写入
python3 scripts/rule_import.py --db data/cache.db --cep-rules ... --dry-run

# 强制重跑（覆盖已有同名规则）
python3 scripts/rule_import.py --db data/cache.db --cep-rules ... --force
```

---

### 数据流水线

```
原始数据（JSON）
  └─ 解析 user_tag → user_profile（用户画像）
  └─ 解析 res_key  → user_raw_events（原始行为）
          ↓ CEP 规则（规则表达式）
     user_derived_events（衍生事件 / Action_*）
          ↓ Need 圈选规则（event.*/profile.*）
     user_need_segments（Need 圈选人群）
          ↓ Need 强度打分（满足度 × 时间衰减 × IDF → Softmax）
     user_need_scores（每用户每 Need 的归一化强度分 + 主导标记）
          ↓ 策略生成
     营销策略（Item ← Need ← Event ← User 链路）
```

---

### Need 强度打分模型

每个用户对每个 Need 的强度由三层相乘，再经 Softmax 归一化：

```
raw_score(user, need) = Fulfillment × TimeDecay × Specificity
```

#### 层1：行为满足度（Fulfillment）

解析 Need 规则引用的 Action 事件列表，按命中次数与各 Action 饱和阈值比较：

```
contribution(action) = min(命中次数 / saturation, 1.0)
Fulfillment = mean(contribution) over all referenced Actions
```

`saturation` 在 `data/cep_rules.action.json` 中每条规则单独配置，例如：
- `Action_Book_Car_Test_Drive`（试驾/联系销售）：`saturation=1`，1次即满分
- `Action_Browse_Car_Detail_Freq`（持续浏览详情）：`saturation=5`，5次才满分
- `Action_Browse_Car_News_Gen`（泛资讯/短视频）：`saturation=8`，低强度行为需8次

#### 层2：时间衰减（TimeDecay）

取该 Need 所有 Action 中最近一次命中时间：

```
TimeDecay = e^{-λ × days_since}，λ = ln2 / halflife_days（默认7天）
```

昨天命中 → TimeDecay ≈ 0.91；14天前命中 → TimeDecay ≈ 0.25

#### 层3：稀缺性/特殊性（Specificity / IDF）

覆盖用户越少的 Need，本底分越高——小众诉求（越野、6座MPV）对应更高的确信度：

```
Specificity = log(N_total / N_need_users)
```

| 示例 Need | 覆盖比例 | IDF（1000用户基准） |
|---|---|---|
| 性价比/折扣（大众诉求）| ~80% | 0.22 |
| 智驾科技偏好 | ~12% | 2.12 |
| 越野性能诉求（小众）| ~3% | 3.51 |

#### 归一化（Softmax）

对每个用户，在其命中的所有 Need 上做 Softmax：
- `normalized_score ∈ (0, 1)`，所有 Need 之和为1
- `dominant_flag=1` 标记得分最高的 Need（该用户的**主导意图**）

#### `user_need_scores` 表结构

```sql
CREATE TABLE user_need_scores (
    user_id          TEXT,
    need_name        TEXT,
    raw_score        REAL,   -- 三层相乘原始分
    normalized_score REAL,   -- Softmax 归一化后（0~1）
    dominant_flag    INTEGER,-- 1=该用户主导 Need，0=非主导
    fulfillment      REAL,   -- 行为满足度（0~1）
    time_decay       REAL,   -- 时间衰减系数（0~1）
    specificity      REAL,   -- IDF 稀缺性分值
    computed_at      TEXT
);
```

---

### `user_raw_events` 表结构

```sql
CREATE TABLE user_raw_events (
    event_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    TEXT,
    event_time TEXT,   -- 原始时间戳（YYYYMMDDHH，如 2025120516）
    time_str   TEXT,   -- 日期（YYYYMMDD，如 20251205）
    dur_time   REAL,   -- 停留时长（秒）
    event_type TEXT,   -- 事件类型（见下表）
    attr_json  TEXT    -- JSON 字符串（各类型字段不同，见下表）
);
```

#### `event_type` 枚举与 `attr_json` 字段

| event_type | 中文含义 | attr_json 字段 | 备注 |
|---|---|---|---|
| `search_vertical` | 搜索三车垂媒 | `brand`、`channel` | brand 无明确品牌时为 `null`；channel 固定 `"三车垂媒"` |
| `search_general` | 搜索泛资讯 | `brand` | 无明确品牌时为 `null` |
| `search_entertainment` | 搜索泛娱乐种草 | `brand`、`model` | 内容平台种草；brand/model 可为 `null` |
| `view_car_detail` | 浏览车辆详情页 | `brand`、`model` | model 可为 `null` |
| `view_car_compare` | 浏览车型对比页 | `brand` | brand 可为 `null` |
| `view_loan_calc` | 浏览车贷计算页 | `brand`、`model` | model 可为 `null` |
| `view_short_video` | 浏览短视频 | `brand` | brand 可为 `null` |
| `view_contact_sales` | 浏览联系销售页 | `brand` | 明确询价意向；brand 可为 `null` |
| `view_floor_price` | 浏览查落地价页 | `brand` | brand 可为 `null` |
| `test_drive` | 试驾 | `model` | model 可为 `null` |
| `order_placed` | 大定（正式下单） | `model` | 购买意向极强 |
| `ad_click` | 广告点击 | `app`、`category`、`brand`、`creative` | app=宿主应用；category=分类#级别；brand/creative 可为 `null` |
| `pass_dealership` | 路过门店 | _(空 `{}`)_ | 线下 LBS 信号 |
| `map_app_use` | 地图/打车软件使用 | _(空 `{}`)_ | |
| `rental_app_use` | 租车软件使用 | _(空 `{}`)_ | |
| `lead_submit` | 留资 | `channel` | `"线下渠道"` / `"线上渠道"`；**正样本标志，规则中禁止引用** |
| `unknown` | 无法识别 | `raw` | 原始 res_key 字符串 |

#### `attr_json` 字段速查

| 字段名 | 出现在哪些 event_type | 含义 | 为 null 的情况 |
|---|---|---|---|
| `brand` | search_vertical/general/entertainment、view_*、ad_click | 品牌名（如"比亚迪"） | 无明确品牌的搜索/浏览 |
| `model` | view_car_detail/loan_calc、search_entertainment、test_drive、order_placed | 车型（如"L9"） | 只有品牌无车型时 |
| `channel` | search_vertical、lead_submit | 渠道来源 | — |
| `app` | ad_click | 宿主 App 名（如"工具"） | — |
| `category` | ad_click | 应用分类#级别（如"浏览器#3"） | — |
| `creative` | ad_click | 创意标签 | 无创意信息时 |
| `raw` | unknown | 原始 res_key | — |

---

### `user_profile` 表结构

```sql
CREATE TABLE user_profile (
    user_id        TEXT PRIMARY KEY,
    gender         TEXT,   -- 男性 / 女性
    age_group      TEXT,   -- 18-24岁 / 24-34岁 / 35-44岁 / 45-54岁
    city           TEXT,   -- 武汉市 等
    city_tier      TEXT,   -- 一线 / 新一线 / 二线 / 三线
    house_status   TEXT,   -- 有房产 / 无房产
    car_status     TEXT,   -- 有车 / 无车
    marital_status TEXT,   -- 已婚 / 未婚
    child_status   TEXT,   -- 已育 / 未育
    consume_freq   TEXT,   -- 较高频 / 中频 / 低频
    device_price   TEXT,   -- 5000~8000 等
    is_lead        INTEGER -- 1=正样本（有留资） 0=负样本
);
```

---

### 规则表达式语法

CEP 规则（`raw.*`）和 Need 圈选规则（`event.*` / `profile.*`）统一使用规则表达式，不使用 SQL。

#### CEP 规则（raw.*）

```
# 计数 / 存在性
raw.search_vertical.count >= 3           # 搜索垂媒次数
raw.view_car_detail.days >= 2            # 浏览详情跨越天数（去重日期数）
raw.search_general.dur_max >= 3000       # 单次最大停留秒数
raw.view_contact_sales.exists            # 是否存在该类事件

# 属性过滤
raw.search_vertical[brand!=null].count >= 2     # 有明确品牌的垂媒搜索次数
raw.view_car_detail[brand].distinct >= 3        # 浏览过几个不同品牌的详情页

# 时序（A 先于 B）
raw.search_vertical.before.view_car_detail.exists

# 跨事件同属性（同品牌既看详情又算车贷）
raw.view_car_detail[brand].same.raw.view_loan_calc[brand].exists

# 逻辑组合
raw.search_vertical.days >= 3 OR raw.search_general.days >= 3
```

#### Need 圈选规则（event.* / profile.*）

```
# 衍生事件（user_derived_events）
event.brand_focused_search.exists
event.multi_day_search.count >= 1

# 用户画像（user_profile）
profile.city_tier IN ['一线', '新一线']
profile.age_group = '35-44岁'

# 组合
event.view_loan_calc.exists AND event.view_car_detail.count >= 1
event.pass_dealership_intent.exists AND profile.city_tier IN ['一线', '新一线']
```

**注意**：所有规则均自动屏蔽 `lead_submit` 事件，防止特征泄露。

---

### 脚本模块说明

| 模块 | 职责 |
|------|------|
| `config.py` | 所有阈值常量（TGI_THRESHOLD、MAX_ROUNDS 等），支持环境变量覆盖 |
| `data_loader.py` | 解析 user_tag / res_key，写入 user_profile + user_raw_events |
| `analytics.py` | CEP 执行、人群规则执行、TGI 计算、因果检验、Need 分值计算（图谱路径 + 规则路径）|
| `ontology.py` | 图谱节点/边操作、序列化/反序列化、LLM prompt 上下文生成 |
| `llm_client.py` | LLM 调用封装、JSON 解析、CEP/Need/Item 推导 |
| `hypothesis.py` | Hypothesis 数据类、多轮假设生成、TGI 验证 |
| `strategy.py` | 营销策略生成（Item←Need←Event←User 链路 + LLM 策略）|
| `rule_expr.py` | 规则表达式解析器与执行器（含 `extract_event_names` 供打分使用）|
| `rule_import.py` | 人工规则导入工具（CEP 规则 + Need 圈选规则）|
| `poc_dual_spiral.py` | 主入口，串联七步流程 |

---

## 两种后端对比

| | Memory 模式（默认） | GraphDB 模式 |
|--|--|--|
| 依赖 | 仅 Python + owlready2 | 需要 Docker + GraphDB |
| 数据规模 | 万级实例 | 百万级以上 |
| 推理方式 | Python 规则引擎 | Python 规则 + OWL RL 内置推理 |
| 持久化 | 无（进程退出即消失） | 有（GraphDB 存储） |
| 适用场景 | 开发、测试、小规模演示 | 生产环境 |
| 切换方式 | `Reasoner()` | `Reasoner(backend="graphdb")` |

---

## 环境变量

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `ONTOLOGY_BACKEND` | `memory` | `memory` 或 `graphdb`，控制查询/推理默认后端 |
| `GRAPHDB_URL` | `http://localhost:7200` | GraphDB 服务地址 |
| `GRAPHDB_REPO` | `auto-marketing` | GraphDB 仓库 ID |
| `ONTOLOGY_IRI` | `http://huawei.com/automotive-marketing-ontology#` | OWL 本体命名空间 |
