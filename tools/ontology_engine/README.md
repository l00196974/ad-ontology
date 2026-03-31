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
