#!/usr/bin/env python3
"""
亿级智能营销 Agent 与本体推理架构 — 双螺旋确权版 POC v4
=======================================================

接入现网真实数据格式：
  - user_tag：Key:Value#Key:Value 编码的用户画像
  - res_key：{动作}_{渠道}_{品牌}{{规格}} 编码的行为事件
  - 正样本：含留资事件的用户；负样本：无留资事件

三层数据流水线：
  层1  原始数据   user_profile（from user_tag）+ user_raw_events（from res_key）
       ↓ CEP规则引擎
  层2  衍生事件   user_derived_events
       ↓ 人群规则引擎
  层3  人群分层   user_segments（含 is_lead 标注）

TGI 语义：留资转化率 TGI = (segment留资率 / 全量留资率) × 100

用法：
    python3 scripts/poc_dual_spiral.py --positive data/positive.json --negative data/negative.json
    python3 scripts/poc_dual_spiral.py  # 无文件时自动生成模拟数据

依赖：sqlite3（stdlib）、networkx、openai（读 llm_config.json）
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import networkx as nx

random.seed(42)

# ─────────────────────────────────────────────────────────────────────────────
# Meta-Ontology 规范（严格白名单，禁止新增）
# ─────────────────────────────────────────────────────────────────────────────

VALID_NODE_TYPES = {"User", "Event", "Need", "Item", "Media"}

VALID_EDGES: dict[str, tuple[set[str], set[str]]] = {
    "Actively_Searches": ({"User"},  {"Item", "Need"}),
    "Highly_Exposed_To": ({"User"},  {"Media"}),
    "Has_Recent_Event":  ({"User"},  {"Event"}),
    "Triggers_Need":     ({"Event"}, {"Need"}),
    "Satisfied_By":      ({"Need"},  {"Item"}),
    "High_CTR_On":       ({"Need"},  {"Media"}),
    "Low_CPA_On":        ({"Need"},  {"Media"}),
}

TGI_THRESHOLD = 120

# ─────────────────────────────────────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────────────────────────────────────

def _sep(title: str = "", width: int = 70) -> None:
    print()
    if title:
        pad = max(0, (width - len(title) - 2) // 2)
        print("=" * pad + f" {title} " + "=" * pad)
    else:
        print("=" * width)

def _step(n: str, desc: str) -> None:
    print(f"\n[{n}] {desc}")
    print("-" * 50)

def add_node(G: nx.DiGraph, name: str, node_type: str, **attrs: Any) -> None:
    if node_type not in VALID_NODE_TYPES:
        raise ValueError(f"非法节点类型: {node_type!r}")
    G.add_node(name, node_type=node_type, **attrs)

def add_edge(G: nx.DiGraph, src: str, dst: str, edge_type: str, **attrs: Any) -> None:
    if edge_type not in VALID_EDGES:
        raise ValueError(f"非法边类型: {edge_type!r}")
    st = G.nodes[src].get("node_type", "")
    dt = G.nodes[dst].get("node_type", "")
    ok_s, ok_d = VALID_EDGES[edge_type]
    if st not in ok_s:
        raise ValueError(f"{edge_type}: src 类型 {st!r} 不合法，需为 {ok_s}")
    if dt not in ok_d:
        raise ValueError(f"{edge_type}: dst 类型 {dt!r} 不合法，需为 {ok_d}")
    G.add_edge(src, dst, edge_type=edge_type, **attrs)

# ─────────────────────────────────────────────────────────────────────────────
# 真实数据解析：user_tag → profile dict
# ─────────────────────────────────────────────────────────────────────────────

_TAG_KEY_MAP = {
    "年龄段":     "age_group",
    "性别":       "gender",
    "房产":       "house_status",
    "购车":       "car_status",
    "城市":       "city",
    "城市等级":   "city_tier",
    "消费频率":   "consume_freq",
    "设备价格":   "device_price",
    "婚恋状态":   "marital_status",
    "育儿状态":   "child_status",
    "天气":       "weather",
    "户外出行倾向": "outdoor_tendency",
    "奢侈品倾向": "luxury_tendency",
    "高品质商品倾向": "quality_tendency",
}

def parse_user_tag(tag_str: str) -> dict:
    """解析 'Key:Value#Key:Value' 格式的 user_tag"""
    result: dict = {v: None for v in _TAG_KEY_MAP.values()}
    if not tag_str:
        return result
    for part in tag_str.split("#"):
        part = part.strip()
        if ":" not in part:
            continue
        k, v = part.split(":", 1)
        field_name = _TAG_KEY_MAP.get(k.strip())
        if field_name:
            result[field_name] = v.strip()
    return result

# ─────────────────────────────────────────────────────────────────────────────
# 真实数据解析：res_key → (event_type, attr_dict)
# ─────────────────────────────────────────────────────────────────────────────

# res_key 格式：动作_渠道_品牌-车型{{规格字段}}
# 或：路过门店 / 地图/打车软件使用 / 留资_线下渠道 等
_RES_KEY_PATTERNS = [
    # 留资
    (re.compile(r"^留资_(.+)$"), "lead_submit"),
    # 搜索_三车垂媒_品牌{{}}
    (re.compile(r"^搜索_三车垂媒_(.+?)\{\{.*\}\}$"), "search_vertical"),
    # 搜索_泛资讯_品牌{{}}
    (re.compile(r"^搜索_泛资讯_(.+?)\{\{.*\}\}$"), "search_general"),
    # 浏览_三车垂媒车辆详情_品牌-车型{{}}
    (re.compile(r"^浏览_三车垂媒车辆详情_(.+?)\{\{(.*)\}\}$"), "view_car_detail"),
    # 浏览_三车垂媒车贷计算_品牌-车型{{}}
    (re.compile(r"^浏览_三车垂媒车贷计算_(.+?)\{\{(.*)\}\}$"), "view_loan_calc"),
    # 路过门店
    (re.compile(r"^路过门店$"), "pass_dealership"),
    # 地图/打车软件
    (re.compile(r"^地图/打车软件使用$"), "map_app_use"),
]

def parse_res_key(res_key: str) -> tuple[str, dict]:
    """返回 (event_type, attr_dict)"""
    res_key = res_key.strip()

    # 留资
    m = re.match(r"^留资_(.+)$", res_key)
    if m:
        return "lead_submit", {"channel": m.group(1)}

    # 搜索_三车垂媒
    m = re.match(r"^搜索_三车垂媒_(.+?)\{\{.*\}\}$", res_key)
    if m:
        brand_raw = m.group(1)
        brand = None if "无明确品牌" in brand_raw else brand_raw
        return "search_vertical", {"brand": brand, "channel": "三车垂媒"}

    # 搜索_泛资讯
    m = re.match(r"^搜索_泛资讯_(.+?)\{\{.*\}\}$", res_key)
    if m:
        brand_raw = m.group(1)
        brand = None if "无明确品牌" in brand_raw else brand_raw
        return "search_general", {"brand": brand}

    # 浏览_车辆详情
    m = re.match(r"^浏览_三车垂媒车辆详情_(.+?)\{\{(.*)\}\}$", res_key)
    if m:
        brand_model = m.group(1)
        parts = brand_model.split("-", 1)
        brand = parts[0] if parts else brand_model
        model = parts[1] if len(parts) > 1 else None
        return "view_car_detail", {"brand": brand, "model": model}

    # 浏览_车贷计算
    m = re.match(r"^浏览_三车垂媒车贷计算_(.+?)\{\{(.*)\}\}$", res_key)
    if m:
        brand_model = m.group(1)
        parts = brand_model.split("-", 1)
        brand = parts[0] if parts else brand_model
        model = parts[1] if len(parts) > 1 else None
        return "view_loan_calc", {"brand": brand, "model": model}

    # 路过门店
    if res_key == "路过门店":
        return "pass_dealership", {}

    # 地图/打车软件
    if "地图" in res_key or "打车" in res_key:
        return "map_app_use", {}

    # 未知
    return "unknown", {"raw": res_key}

# ─────────────────────────────────────────────────────────────────────────────
# 流程 0A：加载数据（真实文件 or 模拟数据）
# ─────────────────────────────────────────────────────────────────────────────

def _init_tables(con: sqlite3.Connection) -> None:
    con.executescript("""
        DROP TABLE IF EXISTS user_profile;
        DROP TABLE IF EXISTS user_raw_events;
        DROP TABLE IF EXISTS user_derived_events;
        DROP TABLE IF EXISTS user_segments;

        CREATE TABLE user_profile (
            user_id      TEXT PRIMARY KEY,
            gender       TEXT,
            age_group    TEXT,
            city         TEXT,
            city_tier    TEXT,
            house_status TEXT,
            car_status   TEXT,
            marital_status TEXT,
            child_status TEXT,
            consume_freq TEXT,
            device_price TEXT,
            is_lead      INTEGER DEFAULT 0
        );

        CREATE TABLE user_raw_events (
            event_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    TEXT,
            event_time TEXT,
            time_str   TEXT,
            dur_time   REAL,
            event_type TEXT,
            attr_json  TEXT
        );

        CREATE TABLE user_derived_events (
            event_id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id           TEXT,
            event_time        TEXT,
            derived_event_type TEXT,
            source_rule       TEXT,
            attr_json         TEXT
        );

        CREATE TABLE user_segments (
            user_id      TEXT,
            segment      TEXT,
            segment_rule TEXT,
            derived_at   TEXT
        );
    """)


def _load_records(records: list[dict], is_lead: int, con: sqlite3.Connection) -> tuple[int, int]:
    """将一批 records 写入 user_profile + user_raw_events，返回 (profile数, event数)"""
    profiles, events = [], []
    for rec in records:
        uid = str(rec.get("user_id", ""))
        tag_str = rec.get("user_tag", "")
        pf = parse_user_tag(tag_str)
        profiles.append((
            uid, pf["gender"], pf["age_group"], pf["city"], pf["city_tier"],
            pf["house_status"], pf["car_status"], pf["marital_status"],
            pf["child_status"], pf["consume_freq"], pf["device_price"], is_lead,
        ))
        for ev in rec.get("user_events", []):
            rk = ev.get("res_key", "")
            etype, attrs = parse_res_key(rk)
            events.append((
                uid,
                str(ev.get("timestamp", "")),
                str(ev.get("time_str", "")),
                float(ev.get("dur_time", 0)),
                etype,
                json.dumps(attrs, ensure_ascii=False),
            ))

    con.executemany(
        "INSERT OR IGNORE INTO user_profile VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        profiles,
    )
    con.executemany(
        "INSERT INTO user_raw_events (user_id,event_time,time_str,dur_time,event_type,attr_json) VALUES (?,?,?,?,?,?)",
        events,
    )
    con.commit()
    return len(profiles), len(events)


def _read_json_file(path: str) -> list[dict]:
    """支持 JSON 数组或 JSON Lines 格式"""
    with open(path, encoding="utf-8") as f:
        content = f.read().strip()
    if content.startswith("["):
        return json.loads(content)
    # JSON Lines
    return [json.loads(line) for line in content.splitlines() if line.strip()]


# ─── 模拟数据生成（无真实文件时的 fallback）─────────────────────────────────

_SIM_BRANDS = ["比亚迪", "理想", "蔚来", "小鹏", "华为问界", "无明确品牌"]
_SIM_CITIES = [("北京", "一线"), ("上海", "一线"), ("武汉", "新一线"),
               ("成都", "新一线"), ("郑州", "二线"), ("洛阳", "三线")]
_SIM_AGES   = ["18-24岁", "24-34岁", "35-44岁", "45-54岁"]
_SIM_RES_KEYS_POS = [
    "搜索_三车垂媒_比亚迪{{ }}",
    "搜索_泛资讯_无明确品牌{{ }}",
    "浏览_三车垂媒车辆详情_理想-L9{{SUV#增程式#39.98万}}",
    "浏览_三车垂媒车贷计算_蔚来-ET5{{轿车#纯电动}}",
    "路过门店",
    "搜索_泛资讯_华为问界{{ }}",
    "路过门店",
    "留资_线下渠道",
]
_SIM_RES_KEYS_NEG = [
    "搜索_泛资讯_无明确品牌{{ }}",
    "地图/打车软件使用",
    "搜索_泛资讯_无明确品牌{{ }}",
]


def _gen_simulated_records(n_pos: int = 500, n_neg: int = 500) -> tuple[list, list]:
    def _make_tag(city, city_tier, age):
        return (f"年龄段:{age}#性别:{'男性' if random.random()>0.4 else '女性'}"
                f"#城市:{city}#城市等级:{city_tier}"
                f"#婚恋状态:{'已婚' if random.random()>0.5 else '未婚'}"
                f"#育儿状态:{'已育' if random.random()>0.5 else '未育'}"
                f"#消费频率:{'较高频' if random.random()>0.5 else '中频'}"
                f"#设备价格:{'5000~8000' if random.random()>0.5 else '3000~5000'}"
                f"#房产:{'有房产' if random.random()>0.6 else '未知'}")

    def _make_events(res_keys: list[str]) -> list[dict]:
        base = datetime(2025, 12, 1)
        evs = []
        for i, rk in enumerate(res_keys):
            dt = base + timedelta(days=random.randint(0, 90), hours=random.randint(0, 23))
            evs.append({
                "timestamp": dt.strftime("%Y%m%d%H"),
                "res_key": rk,
                "time_str": dt.strftime("%Y%m%d"),
                "dur_time": round(random.uniform(0, 5000), 2),
            })
        return evs

    pos_records, neg_records = [], []
    for i in range(n_pos):
        city, tier = random.choice(_SIM_CITIES)
        age = random.choice(_SIM_AGES)
        keys = list(_SIM_RES_KEYS_POS)
        # 随机多几条搜索
        extra = random.randint(0, 4)
        for _ in range(extra):
            brand = random.choice(_SIM_BRANDS)
            keys.insert(random.randint(0, len(keys)-1),
                        f"搜索_泛资讯_{brand}{{{{ }}}}")
        pos_records.append({"user_id": f"pos_{i}", "user_tag": _make_tag(city, tier, age),
                             "user_events": _make_events(keys)})

    for i in range(n_neg):
        city, tier = random.choice(_SIM_CITIES)
        age = random.choice(_SIM_AGES)
        keys = list(_SIM_RES_KEYS_NEG)
        extra = random.randint(0, 3)
        for _ in range(extra):
            keys.append(f"搜索_泛资讯_无明确品牌{{{{ }}}}")
        neg_records.append({"user_id": f"neg_{i}", "user_tag": _make_tag(city, tier, age),
                             "user_events": _make_events(keys)})

    return pos_records, neg_records


def build_raw_data(con: sqlite3.Connection, pos_file: str | None, neg_file: str | None) -> None:
    _sep("流程 0A：原始数据加载")
    _init_tables(con)

    if pos_file and os.path.exists(pos_file) and neg_file and os.path.exists(neg_file):
        _step("0A-1", f"读取正样本文件: {pos_file}")
        pos_records = _read_json_file(pos_file)
        _step("0A-2", f"读取负样本文件: {neg_file}")
        neg_records = _read_json_file(neg_file)
    else:
        _step("0A-0", "未检测到数据文件，自动生成模拟数据（500正+500负）")
        pos_records, neg_records = _gen_simulated_records(500, 500)

    p1, e1 = _load_records(pos_records, 1, con)
    p2, e2 = _load_records(neg_records, 0, con)

    total_p = con.execute("SELECT COUNT(*) FROM user_profile").fetchone()[0]
    total_e = con.execute("SELECT COUNT(*) FROM user_raw_events").fetchone()[0]
    lead_r  = con.execute("SELECT AVG(is_lead) FROM user_profile").fetchone()[0]
    print(f"  正样本用户: {p1:,} 人，事件: {e1:,} 条")
    print(f"  负样本用户: {p2:,} 人，事件: {e2:,} 条")
    print(f"  全量用户: {total_p:,}，全量事件: {total_e:,}")
    print(f"  全量留资率（基线）: {lead_r:.2%}")
    # 事件类型分布
    rows = con.execute(
        "SELECT event_type, COUNT(*) n FROM user_raw_events GROUP BY event_type ORDER BY n DESC"
    ).fetchall()
    print("  事件类型分布:")
    for etype, cnt in rows:
        print(f"    {etype:<25s} {cnt:>7,} 条")

# ─────────────────────────────────────────────────────────────────────────────
# 流程 0B：CEP 规则引擎 → user_derived_events
# ─────────────────────────────────────────────────────────────────────────────

def run_cep_rules(con: sqlite3.Connection) -> None:
    _sep("流程 0B：CEP 规则引擎")

    # 规则1：多日持续搜索 — 搜索事件跨越 ≥ 3 个不同日期
    con.execute("""
        INSERT INTO user_derived_events(user_id, event_time, derived_event_type, source_rule, attr_json)
        SELECT
            user_id,
            MAX(event_time),
            'multi_day_search',
            'R1: 搜索行为跨越>=3个不同日期',
            json_object('search_days', COUNT(DISTINCT time_str), 'total_count', COUNT(*))
        FROM user_raw_events
        WHERE event_type IN ('search_vertical', 'search_general')
        GROUP BY user_id
        HAVING COUNT(DISTINCT time_str) >= 3
    """)

    # 规则2：有明确品牌意向搜索 — 搜索品牌非空 ≥ 2 次
    con.execute("""
        INSERT INTO user_derived_events(user_id, event_time, derived_event_type, source_rule, attr_json)
        SELECT
            user_id,
            MAX(event_time),
            'brand_focused_search',
            'R2: 有明确品牌的搜索>=2次',
            json_object('count', COUNT(*),
                        'brands', GROUP_CONCAT(DISTINCT json_extract(attr_json,'$.brand')))
        FROM user_raw_events
        WHERE event_type IN ('search_vertical', 'search_general')
          AND json_extract(attr_json, '$.brand') IS NOT NULL
        GROUP BY user_id
        HAVING COUNT(*) >= 2
    """)

    # 规则3：详情页 + 车贷计算双重浏览 — 同一用户同时有这两类事件
    con.execute("""
        INSERT INTO user_derived_events(user_id, event_time, derived_event_type, source_rule, attr_json)
        SELECT
            d.user_id,
            MAX(d.event_time),
            'detail_view_with_loan',
            'R3: 浏览车辆详情页且浏览车贷计算页',
            json_object('detail_count', SUM(d.event_type='view_car_detail'),
                        'loan_count',   SUM(d.event_type='view_loan_calc'))
        FROM user_raw_events d
        WHERE d.event_type IN ('view_car_detail', 'view_loan_calc')
        GROUP BY d.user_id
        HAVING SUM(d.event_type='view_car_detail') >= 1
           AND SUM(d.event_type='view_loan_calc')   >= 1
    """)

    # 规则4：高强度路过门店 — pass_dealership ≥ 2 次，或 1 次且 dur_time > 1800s
    con.execute("""
        INSERT INTO user_derived_events(user_id, event_time, derived_event_type, source_rule, attr_json)
        SELECT
            user_id,
            MAX(event_time),
            'pass_dealership_intent',
            'R4: 路过门店>=2次，或1次停留>1800s',
            json_object('count', COUNT(*), 'max_dur', MAX(dur_time))
        FROM user_raw_events
        WHERE event_type = 'pass_dealership'
        GROUP BY user_id
        HAVING COUNT(*) >= 2 OR MAX(dur_time) > 1800
    """)

    # 规则5：高时长搜索 — 单次 search_general dur_time >= 3000s
    con.execute("""
        INSERT INTO user_derived_events(user_id, event_time, derived_event_type, source_rule, attr_json)
        SELECT
            user_id,
            MAX(event_time),
            'high_engagement_search',
            'R5: 单次搜索停留>=3000秒',
            json_object('max_dur', MAX(dur_time), 'count', COUNT(*))
        FROM user_raw_events
        WHERE event_type = 'search_general'
          AND dur_time >= 3000
        GROUP BY user_id
    """)

    con.commit()

    for det, rule in [
        ("multi_day_search",       "R1"),
        ("brand_focused_search",   "R2"),
        ("detail_view_with_loan",  "R3"),
        ("pass_dealership_intent", "R4"),
        ("high_engagement_search", "R5"),
    ]:
        n = con.execute(
            "SELECT COUNT(DISTINCT user_id) FROM user_derived_events WHERE derived_event_type=?",
            (det,)
        ).fetchone()[0]
        lead_r = con.execute("""
            SELECT AVG(p.is_lead) FROM user_derived_events d
            JOIN user_profile p ON d.user_id = p.user_id
            WHERE d.derived_event_type = ?
        """, (det,)).fetchone()[0] or 0
        print(f"  [{rule}] {det:<28s} {n:>6,} 用户  留资率={lead_r:.2%}")


# ─────────────────────────────────────────────────────────────────────────────
# 流程 0C：人群规则引擎 → user_segments
# ─────────────────────────────────────────────────────────────────────────────

SEGMENT_RULES: list[dict] = [
    {
        "segment": "持续搜索型用户",
        "rule_desc": "跨>=3天持续搜索",
        "sql": "SELECT DISTINCT user_id FROM user_derived_events WHERE derived_event_type='multi_day_search'",
    },
    {
        "segment": "品牌意向型用户",
        "rule_desc": "有明确品牌的搜索>=2次",
        "sql": "SELECT DISTINCT user_id FROM user_derived_events WHERE derived_event_type='brand_focused_search'",
    },
    {
        "segment": "深度比价型用户",
        "rule_desc": "同时浏览车辆详情+车贷计算",
        "sql": "SELECT DISTINCT user_id FROM user_derived_events WHERE derived_event_type='detail_view_with_loan'",
    },
    {
        "segment": "到店意向型用户",
        "rule_desc": "高强度路过门店",
        "sql": "SELECT DISTINCT user_id FROM user_derived_events WHERE derived_event_type='pass_dealership_intent'",
    },
    {
        "segment": "高投入搜索型用户",
        "rule_desc": "单次搜索停留>=3000秒",
        "sql": "SELECT DISTINCT user_id FROM user_derived_events WHERE derived_event_type='high_engagement_search'",
    },
]


def run_segment_rules(con: sqlite3.Connection) -> None:
    _sep("流程 0C：人群规则引擎")
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    baseline = con.execute("SELECT AVG(is_lead) FROM user_profile").fetchone()[0] or 0

    for sr in SEGMENT_RULES:
        con.execute(f"""
            INSERT INTO user_segments(user_id, segment, segment_rule, derived_at)
            SELECT user_id, ?, ?, ? FROM ({sr['sql']})
        """, (sr["segment"], sr["rule_desc"], now))
    con.commit()

    for sr in SEGMENT_RULES:
        n = con.execute(
            "SELECT COUNT(*) FROM user_segments WHERE segment=?", (sr["segment"],)
        ).fetchone()[0]
        lead_r = con.execute("""
            SELECT AVG(p.is_lead) FROM user_segments s
            JOIN user_profile p ON s.user_id = p.user_id
            WHERE s.segment = ?
        """, (sr["segment"],)).fetchone()[0] or 0
        tgi = (lead_r / baseline * 100) if baseline > 0 else 0
        print(f"  {sr['segment']:<14s}  {n:>6,} 人  留资率={lead_r:.2%}  TGI={tgi:.0f}")


# ─────────────────────────────────────────────────────────────────────────────
# 流程 1：TBOX 本体初始化（数据驱动）
# ─────────────────────────────────────────────────────────────────────────────

_PRESET_NODES: list[tuple[str, str]] = [
    # Need
    ("购车意向需求",     "Need"),
    ("选车比价需求",     "Need"),
    ("到店体验需求",     "Need"),
    ("品牌偏好需求",     "Need"),
    ("金融方案需求",     "Need"),
    # Item
    ("新能源轿车",       "Item"),
    ("新能源SUV",        "Item"),
    ("豪华品牌车型",     "Item"),
    ("国产新势力车型",   "Item"),
    # Media（暂无媒体数据，占位）
    ("搜索结果广告",     "Media"),
    ("车辆详情页广告",   "Media"),
    ("地图导航广告",     "Media"),
    ("信息流广告",       "Media"),
]


def init_tbox(G: nx.DiGraph, con: sqlite3.Connection) -> None:
    _sep("流程 1：TBOX 本体初始化")
    baseline = con.execute("SELECT AVG(is_lead) FROM user_profile").fetchone()[0] or 0

    # User 节点：数据驱动（来自 user_segments）
    segs = con.execute(
        "SELECT segment, segment_rule, COUNT(*) FROM user_segments GROUP BY segment"
    ).fetchall()
    for seg, rule, cnt in segs:
        lead_r = con.execute("""
            SELECT AVG(p.is_lead) FROM user_segments s
            JOIN user_profile p ON s.user_id=p.user_id WHERE s.segment=?
        """, (seg,)).fetchone()[0] or 0
        tgi = lead_r / baseline * 100 if baseline > 0 else 0
        add_node(G, seg, "User", segment_rule=rule, user_count=cnt,
                 lead_rate=round(lead_r, 4), tgi=round(tgi, 1))
        print(f"  [User ] {seg:<16s} {cnt:>6,} 人  留资率={lead_r:.2%}  TGI={tgi:.0f}")

    # Event 节点：数据驱动（来自 user_derived_events）
    evts = con.execute("""
        SELECT derived_event_type, source_rule, COUNT(DISTINCT user_id)
        FROM user_derived_events GROUP BY derived_event_type
    """).fetchall()
    for det, rule, cnt in evts:
        add_node(G, det, "Event", source_rule=rule, user_count=cnt)
        print(f"  [Event] {det:<28s} {cnt:>6,} 用户")

    # Need/Item/Media 预定义
    for name, ntype in _PRESET_NODES:
        add_node(G, name, ntype)

    need_names  = [n for n, d in G.nodes(data=True) if d["node_type"] == "Need"]
    item_names  = [n for n, d in G.nodes(data=True) if d["node_type"] == "Item"]
    media_names = [n for n, d in G.nodes(data=True) if d["node_type"] == "Media"]
    print(f"\n  [Need ] {', '.join(need_names)}")
    print(f"  [Item ] {', '.join(item_names)}")
    print(f"  [Media] {', '.join(media_names)}")
    print(f"\n  合法边类型: {list(VALID_EDGES.keys())}")


# ─────────────────────────────────────────────────────────────────────────────
# LLM 工具函数
# ─────────────────────────────────────────────────────────────────────────────

_LLM_CONFIG: dict | None = None
_LLM_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "llm_config.json")


def _load_llm_config() -> dict | None:
    global _LLM_CONFIG
    if _LLM_CONFIG is not None:
        return _LLM_CONFIG
    if os.path.exists(_LLM_CONFIG_PATH):
        with open(_LLM_CONFIG_PATH, encoding="utf-8") as f:
            _LLM_CONFIG = json.load(f)
        return _LLM_CONFIG
    return None


def _llm_call(prompt: str) -> str | None:
    cfg = _load_llm_config()
    if not cfg or not cfg.get("api_key"):
        return None
    try:
        from openai import OpenAI
        client = OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"])
        resp = client.chat.completions.create(
            model=cfg["model"],
            max_tokens=cfg.get("max_tokens", 2048),
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content
    except Exception as e:
        print(f"  [LLM] 调用失败：{e}")
        return None


def _ontology_ctx(G: nx.DiGraph) -> str:
    lines = []
    for ntype in ["User", "Event", "Need", "Item", "Media"]:
        names = [n for n, d in G.nodes(data=True) if d.get("node_type") == ntype]
        lines.append(f"  {ntype}: {', '.join(names)}")
    edge_lines = [f"  {et}: {list(sv)} → {list(dv)}" for et, (sv, dv) in VALID_EDGES.items()]
    return ("【节点（按类型）】\n" + "\n".join(lines) +
            "\n\n【合法边类型（严禁新增）】\n" + "\n".join(edge_lines))


# ─────────────────────────────────────────────────────────────────────────────
# 流程 2：LLM 假设生成（双螺旋螺旋 A）
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Hypothesis:
    id: str
    description: str
    source_node: str
    target_node: str
    edge_type: str
    target_segment: str
    feature_event: str
    tgi: float = 0.0
    confirmed: bool = False
    source: str = "llm"


FALLBACK_HYPOTHESES: list[dict] = [
    {
        "id": "H1", "source": "fallback",
        "description": "持续搜索型用户具有多日持续搜索衍生事件",
        "source_node": "持续搜索型用户", "target_node": "multi_day_search",
        "edge_type": "Has_Recent_Event",
        "target_segment": "持续搜索型用户", "feature_event": "multi_day_search",
    },
    {
        "id": "H2", "source": "fallback",
        "description": "多日持续搜索触发购车意向需求",
        "source_node": "multi_day_search", "target_node": "购车意向需求",
        "edge_type": "Triggers_Need",
        "target_segment": "持续搜索型用户", "feature_event": "multi_day_search",
    },
    {
        "id": "H3", "source": "fallback",
        "description": "深度比价型用户具有详情+车贷双重浏览事件",
        "source_node": "深度比价型用户", "target_node": "detail_view_with_loan",
        "edge_type": "Has_Recent_Event",
        "target_segment": "深度比价型用户", "feature_event": "detail_view_with_loan",
    },
    {
        "id": "H4", "source": "fallback",
        "description": "详情+车贷双重浏览触发金融方案需求",
        "source_node": "detail_view_with_loan", "target_node": "金融方案需求",
        "edge_type": "Triggers_Need",
        "target_segment": "深度比价型用户", "feature_event": "detail_view_with_loan",
    },
    {
        "id": "H5", "source": "fallback",
        "description": "到店意向型用户具有高强度路过门店事件",
        "source_node": "到店意向型用户", "target_node": "pass_dealership_intent",
        "edge_type": "Has_Recent_Event",
        "target_segment": "到店意向型用户", "feature_event": "pass_dealership_intent",
    },
]


def generate_hypotheses(G: nx.DiGraph, con: sqlite3.Connection) -> list[Hypothesis]:
    _sep("流程 2：LLM 假设生成（螺旋 A）")

    seg_stats = con.execute("""
        SELECT s.segment, COUNT(*) n, AVG(p.is_lead) lead_rate
        FROM user_segments s JOIN user_profile p ON s.user_id=p.user_id
        GROUP BY s.segment ORDER BY lead_rate DESC
    """).fetchall()
    evt_stats = con.execute("""
        SELECT d.derived_event_type, COUNT(DISTINCT d.user_id) n, AVG(p.is_lead) lead_rate
        FROM user_derived_events d JOIN user_profile p ON d.user_id=p.user_id
        GROUP BY d.derived_event_type ORDER BY lead_rate DESC
    """).fetchall()
    baseline = con.execute("SELECT AVG(is_lead) FROM user_profile").fetchone()[0] or 0

    seg_summary = "\n".join(
        f"  {r[0]}: {r[1]:,}人  留资率={r[2]:.2%}  TGI={r[2]/baseline*100:.0f}" for r in seg_stats
    )
    evt_summary = "\n".join(
        f"  {r[0]}: {r[1]:,}用户  留资率={r[2]:.2%}  TGI={r[2]/baseline*100:.0f}" for r in evt_stats
    )

    prompt = f"""你是一个智能营销数据挖掘专家。我们正在挖掘汽车留资线索人群（有购车留资意向的用户）。
请严格遵循本体规范，提出 5 条可用数据验证的关系挖掘假设。

{_ontology_ctx(G)}

【人群分层统计（user_segments，含留资率 TGI）】
{seg_summary}

【衍生事件统计（user_derived_events，含留资率 TGI）】
{evt_summary}

【全量留资基线】留资率={baseline:.2%}

【重要约束】
1. source_node 和 target_node 必须是上面已列出的节点名称，不得新创节点
2. edge_type 必须是合法边类型之一
3. Has_Recent_Event 只能 User→Event；Triggers_Need 只能 Event→Need
4. target_segment 必须是人群分层中的 segment 值
5. feature_event 必须是衍生事件中的 derived_event_type 值
6. 优先选择 TGI 高（>120）的路径，这些路径对留资预测价值更大

返回 JSON 数组，每条包含：id, description, source_node, target_node, edge_type, target_segment, feature_event
只返回 JSON，不要其他文字。"""

    raw = _llm_call(prompt)
    raw_list: list[dict] = []
    if raw:
        try:
            s, e = raw.find("["), raw.rfind("]") + 1
            raw_list = json.loads(raw[s:e])
            print(f"  [LLM] 生成 {len(raw_list)} 条假设")
        except Exception as ex:
            print(f"  [LLM] JSON 解析失败：{ex}，使用 fallback")
    else:
        print("  [FALLBACK] 无 LLM 配置，使用内置留资挖掘假设")
        raw_list = FALLBACK_HYPOTHESES

    if not raw_list:
        raw_list = FALLBACK_HYPOTHESES

    result = []
    for i, h in enumerate(raw_list):
        hyp = Hypothesis(
            id=h.get("id") or f"H{i+1}",
            description=h.get("description", ""),
            source_node=h.get("source_node", ""),
            target_node=h.get("target_node", ""),
            edge_type=h.get("edge_type", ""),
            target_segment=h.get("target_segment", ""),
            feature_event=h.get("feature_event", ""),
            source=h.get("source", "llm"),
        )
        flag = "[FALLBACK]" if hyp.source == "fallback" else "[LLM]    "
        print(f"  {flag} [{hyp.id}] {hyp.description}")
        print(f"           {hyp.source_node} --[{hyp.edge_type}]--> {hyp.target_node}")
        result.append(hyp)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# 流程 3：ABOX TGI 验证 + 算力确权（双螺旋螺旋 B）
# TGI = (segment留资率 / 全量留资率) × 100  ≥ 120 才确权
# ─────────────────────────────────────────────────────────────────────────────

def _compute_tgi(con: sqlite3.Connection, target_segment: str, feature_event: str) -> float:
    baseline = con.execute("SELECT AVG(is_lead) FROM user_profile").fetchone()[0] or 0
    if baseline == 0:
        return 0.0
    # segment 中有 feature_event 的用户的留资率
    seg_lead_r = con.execute("""
        SELECT AVG(p.is_lead)
        FROM user_segments s
        JOIN user_derived_events d ON s.user_id = d.user_id AND d.derived_event_type = ?
        JOIN user_profile p ON s.user_id = p.user_id
        WHERE s.segment = ?
    """, (feature_event, target_segment)).fetchone()[0] or 0
    return (seg_lead_r / baseline) * 100


def validate_hypotheses(
    hypotheses: list[Hypothesis], con: sqlite3.Connection, G: nx.DiGraph
) -> list[Hypothesis]:
    _sep("流程 3：ABOX TGI 验证 + 算力确权（螺旋 B）")
    confirmed = []
    for h in hypotheses:
        if h.source_node not in G.nodes:
            print(f"  [{h.id}] ⚠  source_node 不在图谱: {h.source_node}")
            continue
        if h.target_node not in G.nodes:
            print(f"  [{h.id}] ⚠  target_node 不在图谱: {h.target_node}")
            continue
        seg_ok = con.execute(
            "SELECT 1 FROM user_segments WHERE segment=? LIMIT 1", (h.target_segment,)
        ).fetchone()
        if not seg_ok:
            print(f"  [{h.id}] ⚠  segment 不存在: {h.target_segment}")
            continue
        h.tgi = round(_compute_tgi(con, h.target_segment, h.feature_event), 1)
        h.confirmed = h.tgi >= TGI_THRESHOLD
        status = "✅ 确权" if h.confirmed else "❌ 否决"
        print(f"  [{h.id}] TGI={h.tgi:6.1f}  {status}  {h.description}")
        if h.confirmed:
            try:
                add_edge(G, h.source_node, h.target_node, h.edge_type,
                         tgi=h.tgi, hypothesis_id=h.id)
                print(f"         → 写入图谱: {h.source_node} --[{h.edge_type}]--> {h.target_node}")
                confirmed.append(h)
            except ValueError as e:
                print(f"         ⚠  合规校验失败: {e}")
    print(f"\n  图谱节点数: {G.number_of_nodes()}，确权边数: {G.number_of_edges()}")
    return confirmed


# ─────────────────────────────────────────────────────────────────────────────
# 流程 4：LLM 营销策略生成
# ─────────────────────────────────────────────────────────────────────────────

def generate_strategies(
    confirmed: list[Hypothesis], G: nx.DiGraph, con: sqlite3.Connection
) -> None:
    _sep("流程 4：LLM 营销策略生成")
    if not confirmed:
        print("  无确权假设，跳过策略生成")
        return

    baseline = con.execute("SELECT AVG(is_lead) FROM user_profile").fetchone()[0] or 0
    edge_lines = []
    for h in confirmed:
        n = con.execute(
            "SELECT COUNT(*) FROM user_segments WHERE segment=?", (h.target_segment,)
        ).fetchone()[0]
        lead_r = con.execute("""
            SELECT AVG(p.is_lead) FROM user_segments s
            JOIN user_profile p ON s.user_id=p.user_id WHERE s.segment=?
        """, (h.target_segment,)).fetchone()[0] or 0
        edge_lines.append(
            f"  {h.source_node} --[{h.edge_type}]--> {h.target_node}"
            f"  (TGI={h.tgi:.0f}, 人群={n:,}人, 留资率={lead_r:.2%})"
        )

    prompt = f"""你是汽车营销策略专家。我们的目标是找到并触达有购车留资意向的用户。

{_ontology_ctx(G)}

【已确权图谱边（TGI≥{TGI_THRESHOLD}，留资转化率显著）】
{chr(10).join(edge_lines)}

【全量留资基线】留资率={baseline:.2%}

请为每条确权路径生成营销策略，JSON 数组，每条包含：
- segment_name: 目标人群
- insight: 该人群的行为洞察（结合事件特征）
- need_path: 图谱路径（如: 持续搜索型用户→multi_day_search→购车意向需求）
- ad_channel: 推荐投放渠道（对应 Media 节点）
- ad_creative: 广告创意建议（结合 Item 节点的车型特征）
- budget_priority: P0/P1/P2 + 理由
- explainability: 引用 TGI 和图谱路径的可解释性说明

只返回 JSON，不要其他文字。"""

    raw = _llm_call(prompt)
    strategies = []
    if raw:
        try:
            s, e = raw.find("["), raw.rfind("]") + 1
            strategies = json.loads(raw[s:e])
            print(f"  [LLM] 生成 {len(strategies)} 条策略\n")
        except Exception as ex:
            print(f"  [LLM] 解析失败: {ex}")

    if not strategies:
        print("  [FALLBACK] 生成基础策略\n")
        for h in confirmed:
            n = con.execute(
                "SELECT COUNT(*) FROM user_segments WHERE segment=?", (h.target_segment,)
            ).fetchone()[0]
            lead_r = con.execute("""
                SELECT AVG(p.is_lead) FROM user_segments s
                JOIN user_profile p ON s.user_id=p.user_id WHERE s.segment=?
            """, (h.target_segment,)).fetchone()[0] or 0
            strategies.append({
                "segment_name": h.target_segment,
                "insight": f"该人群具有 {h.feature_event} 行为特征，留资率={lead_r:.2%}",
                "need_path": f"{h.source_node} → {h.target_node}",
                "ad_channel": "搜索结果广告",
                "ad_creative": "结合用户搜索的品牌和车型，突出金融方案/到店优惠",
                "budget_priority": f"P{'0' if h.tgi >= 150 else '1'}",
                "explainability": f"TGI={h.tgi:.0f}（基线留资率={baseline:.2%}），人群规模={n:,}人",
            })

    for s in strategies:
        print(f"## {s.get('segment_name', '')}")
        print(f"  洞察: {s.get('insight', '')}")
        print(f"  链路: {s.get('need_path', '')}")
        print(f"  渠道: {s.get('ad_channel', '')}")
        print(f"  创意: {s.get('ad_creative', '')}")
        print(f"  预算: {s.get('budget_priority', '')}")
        print(f"  解释: {s.get('explainability', '')}\n")


# ─────────────────────────────────────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="双螺旋确权 POC v4 — 留资线索人群挖掘")
    parser.add_argument("--positive", default=None, help="正样本 JSON 文件路径")
    parser.add_argument("--negative", default=None, help="负样本 JSON 文件路径")
    args = parser.parse_args()

    _sep("双螺旋确权 POC v4 — 留资线索人群挖掘")
    print("三层流水线: 原始事件(res_key) → CEP衍生事件 → 人群分层 → TBOX图谱 → LLM策略")

    con = sqlite3.connect(":memory:")
    G   = nx.DiGraph()

    build_raw_data(con, args.positive, args.negative)
    run_cep_rules(con)
    run_segment_rules(con)
    init_tbox(G, con)
    hypotheses = generate_hypotheses(G, con)
    confirmed  = validate_hypotheses(hypotheses, con, G)
    generate_strategies(confirmed, G, con)

    _sep("POC 运行完毕")
    print(f"  确权假设: {len(confirmed)} / {len(hypotheses)}")
    print(f"  TBOX 图谱边数: {G.number_of_edges()}")
    _sep()


if __name__ == "__main__":
    main()



