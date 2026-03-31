#!/usr/bin/env python3
"""
亿级智能营销 Agent 与本体推理架构 — 双螺旋确权版 POC v4
=======================================================

接入现网真实数据格式，完整七步流程：
  流程 0A  原始数据加载（user_tag / res_key 解析）
  流程 0B  LLM 推导 CEP 规则 → user_derived_events（非硬编码）
  流程 0C  人群规则引擎 → user_segments
  流程 1   TBOX 本体初始化（User/Event 数据驱动；Need/Item/Media LLM 推导）
  流程 2   多轮 LLM 假设生成（螺旋 A，最多 3 轮直到 TGI 达标）
  流程 3   ABOX TGI 验证 + 因果检验 + 算力确权（螺旋 B）
  流程 4   LLM 营销策略生成

用法：
    python3 scripts/poc_dual_spiral.py --positive data/positive.json --negative data/negative.json
    python3 scripts/poc_dual_spiral.py --positive ... --negative ... --reset   # 重新初始化DB
    python3 scripts/poc_dual_spiral.py --positive ... --dump-unknown           # 打印未识别事件

依赖：sqlite3（stdlib）、networkx、openai（读 llm_config.json）
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import random
import re
import sqlite3
from dataclasses import dataclass
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

TGI_THRESHOLD   = 120
MAX_ROUNDS      = 3   # 多轮推理最大轮数
MIN_CONFIRMED   = 3   # 每轮至少确权多少条才停止

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
        raise ValueError(f"{edge_type}: src={st!r} 不合法，需为 {ok_s}")
    if dt not in ok_d:
        raise ValueError(f"{edge_type}: dst={dt!r} 不合法，需为 {ok_d}")
    G.add_edge(src, dst, edge_type=edge_type, **attrs)

# ─────────────────────────────────────────────────────────────────────────────
# user_tag 解析
# ─────────────────────────────────────────────────────────────────────────────

_TAG_KEY_MAP = {
    "年龄段": "age_group", "性别": "gender", "房产": "house_status",
    "购车": "car_status", "城市": "city", "城市等级": "city_tier",
    "消费频率": "consume_freq", "设备价格": "device_price",
    "婚恋状态": "marital_status", "育儿状态": "child_status",
    "天气": "weather", "户外出行倾向": "outdoor_tendency",
    "奢侈品倾向": "luxury_tendency", "高品质商品倾向": "quality_tendency",
}

def parse_user_tag(tag_str: str) -> dict:
    result = {v: None for v in _TAG_KEY_MAP.values()}
    for part in (tag_str or "").split("#"):
        if ":" not in part:
            continue
        k, v = part.strip().split(":", 1)
        field = _TAG_KEY_MAP.get(k.strip())
        if field:
            result[field] = v.strip()
    return result

# ─────────────────────────────────────────────────────────────────────────────
# res_key 解析
# ─────────────────────────────────────────────────────────────────────────────

def parse_res_key(res_key: str) -> tuple[str, dict]:
    rk = (res_key or "").strip()
    m = re.match(r"^留资_(.+)$", rk)
    if m:
        return "lead_submit", {"channel": m.group(1)}
    m = re.match(r"^搜索_三车垂媒_(.+?)\{\{.*\}\}$", rk)
    if m:
        brand_raw = m.group(1)
        brand = None if "无明确品牌" in brand_raw else brand_raw
        return "search_vertical", {"brand": brand, "channel": "三车垂媒"}
    m = re.match(r"^搜索_泛资讯_(.+?)\{\{.*\}\}$", rk)
    if m:
        brand_raw = m.group(1)
        brand = None if "无明确品牌" in brand_raw else brand_raw
        return "search_general", {"brand": brand}
    m = re.match(r"^浏览_三车垂媒车辆详情_(.+?)\{\{.*\}\}$", rk)
    if m:
        parts = m.group(1).split("-", 1)
        return "view_car_detail", {"brand": parts[0], "model": parts[1] if len(parts) > 1 else None}
    m = re.match(r"^浏览_三车垂媒车贷计算_(.+?)\{\{.*\}\}$", rk)
    if m:
        parts = m.group(1).split("-", 1)
        return "view_loan_calc", {"brand": parts[0], "model": parts[1] if len(parts) > 1 else None}
    if rk == "路过门店":
        return "pass_dealership", {}
    if "地图" in rk or "打车" in rk:
        return "map_app_use", {}
    return "unknown", {"raw": rk}

# ─────────────────────────────────────────────────────────────────────────────
# 流程 0A：数据加载
# ─────────────────────────────────────────────────────────────────────────────

def _init_tables(con: sqlite3.Connection) -> None:
    con.executescript("""
        DROP TABLE IF EXISTS user_profile;
        DROP TABLE IF EXISTS user_raw_events;
        DROP TABLE IF EXISTS user_derived_events;
        DROP TABLE IF EXISTS user_segments;
        CREATE TABLE user_profile (
            user_id TEXT PRIMARY KEY, gender TEXT, age_group TEXT,
            city TEXT, city_tier TEXT, house_status TEXT, car_status TEXT,
            marital_status TEXT, child_status TEXT, consume_freq TEXT,
            device_price TEXT, is_lead INTEGER DEFAULT 0
        );
        CREATE TABLE user_raw_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT, event_time TEXT, time_str TEXT,
            dur_time REAL, event_type TEXT, attr_json TEXT
        );
        CREATE TABLE user_derived_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT, event_time TEXT,
            derived_event_type TEXT, source_rule TEXT, attr_json TEXT
        );
        CREATE TABLE user_segments (
            user_id TEXT, segment TEXT, segment_rule TEXT, derived_at TEXT
        );
    """)

def _read_json_file(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        content = f.read().strip()
    if content.startswith("["):
        return json.loads(content)
    return [json.loads(line) for line in content.splitlines() if line.strip()]

def _load_records(records: list[dict], is_lead: int, con: sqlite3.Connection) -> tuple[int, int]:
    profiles, events = [], []
    for rec in records:
        uid = str(rec.get("user_id", ""))
        pf  = parse_user_tag(rec.get("user_tag", ""))
        profiles.append((uid, pf["gender"], pf["age_group"], pf["city"], pf["city_tier"],
                         pf["house_status"], pf["car_status"], pf["marital_status"],
                         pf["child_status"], pf["consume_freq"], pf["device_price"], is_lead))
        for ev in rec.get("user_events", []):
            etype, attrs = parse_res_key(ev.get("res_key", ""))
            events.append((uid, str(ev.get("timestamp", "")), str(ev.get("time_str", "")),
                           float(ev.get("dur_time", 0) or 0), etype,
                           json.dumps(attrs, ensure_ascii=False)))
    con.executemany("INSERT OR IGNORE INTO user_profile VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", profiles)
    con.executemany(
        "INSERT INTO user_raw_events(user_id,event_time,time_str,dur_time,event_type,attr_json)"
        " VALUES (?,?,?,?,?,?)", events)
    con.commit()
    return len(profiles), len(events)

def build_raw_data(con: sqlite3.Connection, pos_file: str | None,
                   neg_file: str | None, dump_unknown: bool = False) -> None:
    _sep("流程 0A：原始数据加载")
    _init_tables(con)

    if not pos_file and not neg_file:
        print("  [0A-0] 未提供数据文件，生成模拟数据（500正+500负）")
        pos_recs, neg_recs = _gen_simulated_records(500, 500)
        _load_records(pos_recs, 1, con)
        _load_records(neg_recs, 0, con)
    else:
        if pos_file and os.path.exists(pos_file):
            print(f"  [0A-1] 读取正样本: {pos_file}")
            p, e = _load_records(_read_json_file(pos_file), 1, con)
            print(f"         {p:,} 用户，{e:,} 事件")
        if neg_file and os.path.exists(neg_file):
            print(f"  [0A-2] 读取负样本: {neg_file}")
            p, e = _load_records(_read_json_file(neg_file), 0, con)
            print(f"         {p:,} 用户，{e:,} 事件")

    total_p  = con.execute("SELECT COUNT(*) FROM user_profile").fetchone()[0]
    total_e  = con.execute("SELECT COUNT(*) FROM user_raw_events").fetchone()[0]
    baseline = con.execute("SELECT AVG(is_lead) FROM user_profile").fetchone()[0] or 0
    print(f"\n  全量用户: {total_p:,}，全量事件: {total_e:,}，留资基线: {baseline:.2%}")

    # 事件类型分布（含 unknown）
    rows = con.execute(
        "SELECT event_type, COUNT(*) n FROM user_raw_events GROUP BY event_type ORDER BY n DESC"
    ).fetchall()
    print("  事件类型分布:")
    for etype, cnt in rows:
        pct = cnt / total_e * 100
        print(f"    {etype:<25s} {cnt:>9,} 条  ({pct:.1f}%)")

    # --dump-unknown：打印未识别事件的 Top 50 样本
    if dump_unknown:
        _sep("DUMP：未识别事件 Top 50 样本")
        unk_rows = con.execute("""
            SELECT attr_json, COUNT(*) n
            FROM user_raw_events WHERE event_type='unknown'
            GROUP BY attr_json ORDER BY n DESC LIMIT 50
        """).fetchall()
        if unk_rows:
            for attr_json, cnt in unk_rows:
                raw = json.loads(attr_json).get("raw", "")
                print(f"  {cnt:>8,}  {raw}")
        else:
            print("  无 unknown 事件")

# ─────────────────────────────────────────────────────────────────────────────
# LLM 工具
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

def _llm_call(prompt: str) -> str | None:
    cfg = _load_llm_config()
    if not cfg or not cfg.get("api_key"):
        return None
    try:
        from openai import OpenAI
        client = OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"])
        resp = client.chat.completions.create(
            model=cfg["model"],
            max_tokens=cfg.get("max_tokens", 4096),
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content
    except Exception as e:
        print(f"  [LLM] 调用失败: {e}")
        return None

def _parse_json_block(text: str) -> list | dict | None:
    """从 LLM 返回中提取第一个 JSON 数组或对象"""
    for start, end in [("[", "]"), ("{", "}")]:
        s = text.find(start)
        e = text.rfind(end) + 1
        if s >= 0 and e > s:
            try:
                return json.loads(text[s:e])
            except Exception:
                pass
    return None

def _ontology_ctx(G: nx.DiGraph) -> str:
    lines = []
    for ntype in ["User", "Event", "Need", "Item", "Media"]:
        names = [n for n, d in G.nodes(data=True) if d.get("node_type") == ntype]
        lines.append(f"  {ntype}: {', '.join(names) or '（暂无）'}")
    edge_lines = [f"  {et}: {list(sv)} → {list(dv)}" for et, (sv, dv) in VALID_EDGES.items()]
    return ("【节点（按类型）】\n" + "\n".join(lines) +
            "\n\n【合法边类型（严禁新增）】\n" + "\n".join(edge_lines))

# ─────────────────────────────────────────────────────────────────────────────
# 流程 0B：LLM 推导 CEP 规则 → user_derived_events
# ─────────────────────────────────────────────────────────────────────────────

# 内置保底 CEP 规则（LLM 失败时使用）
_BUILTIN_CEP_RULES = [
    {
        "name": "multi_day_search",
        "desc": "搜索行为跨越>=3个不同日期",
        "sql": """
            INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
            SELECT user_id, MAX(event_time), 'multi_day_search',
                   '搜索行为跨越>=3个不同日期',
                   json_object('search_days',COUNT(DISTINCT time_str),'total_count',COUNT(*))
            FROM user_raw_events
            WHERE event_type IN ('search_vertical','search_general')
            GROUP BY user_id HAVING COUNT(DISTINCT time_str) >= 3
        """,
    },
    {
        "name": "brand_focused_search",
        "desc": "有明确品牌意向的搜索>=2次",
        "sql": """
            INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
            SELECT user_id, MAX(event_time), 'brand_focused_search',
                   '有明确品牌意向的搜索>=2次',
                   json_object('count',COUNT(*),
                               'brands',GROUP_CONCAT(DISTINCT json_extract(attr_json,'$.brand')))
            FROM user_raw_events
            WHERE event_type IN ('search_vertical','search_general')
              AND json_extract(attr_json,'$.brand') IS NOT NULL
            GROUP BY user_id HAVING COUNT(*) >= 2
        """,
    },
    {
        "name": "detail_view_with_loan",
        "desc": "同时浏览车辆详情页且浏览车贷计算页",
        "sql": """
            INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
            SELECT user_id, MAX(event_time), 'detail_view_with_loan',
                   '同时浏览车辆详情页且浏览车贷计算页',
                   json_object('detail_count',SUM(event_type='view_car_detail'),
                               'loan_count',SUM(event_type='view_loan_calc'))
            FROM user_raw_events
            WHERE event_type IN ('view_car_detail','view_loan_calc')
            GROUP BY user_id
            HAVING SUM(event_type='view_car_detail')>=1 AND SUM(event_type='view_loan_calc')>=1
        """,
    },
    {
        "name": "pass_dealership_intent",
        "desc": "路过门店>=2次，或1次停留>1800s",
        "sql": """
            INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
            SELECT user_id, MAX(event_time), 'pass_dealership_intent',
                   '路过门店>=2次，或1次停留>1800s',
                   json_object('count',COUNT(*),'max_dur',MAX(dur_time))
            FROM user_raw_events
            WHERE event_type='pass_dealership'
            GROUP BY user_id HAVING COUNT(*)>=2 OR MAX(dur_time)>1800
        """,
    },
    {
        "name": "high_engagement_search",
        "desc": "单次搜索停留>=3000秒",
        "sql": """
            INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
            SELECT user_id, MAX(event_time), 'high_engagement_search',
                   '单次搜索停留>=3000秒',
                   json_object('max_dur',MAX(dur_time),'count',COUNT(*))
            FROM user_raw_events
            WHERE event_type='search_general' AND dur_time>=3000
            GROUP BY user_id
        """,
    },
]


def _llm_derive_cep_rules(con: sqlite3.Connection) -> list[dict] | None:
    """让 LLM 根据事件分布推导 CEP 规则，返回规则列表或 None"""
    # 统计各 event_type 的分布和留资率
    rows = con.execute("""
        SELECT e.event_type,
               COUNT(*) total_events,
               COUNT(DISTINCT e.user_id) users,
               AVG(p.is_lead) lead_rate
        FROM user_raw_events e
        JOIN user_profile p ON e.user_id=p.user_id
        WHERE e.event_type != 'lead_submit'
        GROUP BY e.event_type ORDER BY total_events DESC
    """).fetchall()
    baseline = con.execute("SELECT AVG(is_lead) FROM user_profile").fetchone()[0] or 0

    # 各类事件的 dur_time 分布
    dur_rows = con.execute("""
        SELECT event_type,
               ROUND(AVG(dur_time),1) avg_dur,
               ROUND(MAX(dur_time),1) max_dur,
               ROUND(MIN(dur_time),1) min_dur
        FROM user_raw_events WHERE dur_time>0
        GROUP BY event_type ORDER BY avg_dur DESC
    """).fetchall()

    event_dist = "\n".join(
        f"  {r[0]:<25s} 事件数={r[1]:,} 用户数={r[2]:,} 留资率={r[3]:.2%}"
        for r in rows
    )
    dur_dist = "\n".join(
        f"  {r[0]:<25s} avg_dur={r[1]}s  max_dur={r[2]}s"
        for r in dur_rows
    )

    prompt = f"""你是汽车营销数据挖掘专家。根据以下用户行为事件的统计分布，推导 CEP（复杂事件处理）规则，
用于从原始事件中计算"高购车意向"的衍生事件，以便识别留资线索用户。

【事件类型分布（含留资率）】
{event_dist}

【事件停留时长分布（秒）】
{dur_dist}

【全量留资基线】{baseline:.2%}

【可用的原始事件类型】
  search_vertical（垂直媒体搜索）, search_general（泛资讯搜索）,
  view_car_detail（浏览车辆详情）, view_loan_calc（浏览车贷计算）,
  pass_dealership（路过门店）, map_app_use（地图/打车软件）

【要求】
1. 推导 5~8 条 CEP 规则，每条规则产生一个新的衍生事件类型（derived_event_type）
2. 规则必须能直接翻译为 SQL GROUP BY + HAVING 语句（基于 user_raw_events 表）
3. 衍生事件名称使用英文下划线（如 multi_day_search）
4. 规则阈值要基于上面的数据分布来设定，而非拍脑袋
5. 留资率高于基线的事件组合优先作为触发条件

【user_raw_events 表结构】
  user_id TEXT, event_time TEXT, time_str TEXT(YYYYMMDD),
  dur_time REAL(秒), event_type TEXT, attr_json TEXT

返回 JSON 数组，每条包含：
  name（衍生事件名）, desc（中文描述）, sql（INSERT INTO user_derived_events 的完整SQL）

SQL 模板：
  INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
  SELECT user_id, MAX(event_time), '<name>', '<desc>', json_object(...)
  FROM user_raw_events WHERE ... GROUP BY user_id HAVING ...

只返回 JSON，不要其他文字。"""

    raw = _llm_call(prompt)
    if not raw:
        return None
    result = _parse_json_block(raw)
    if isinstance(result, list) and result:
        # 基本校验：每条规则有 name/desc/sql
        valid = [r for r in result if r.get("name") and r.get("sql")]
        if valid:
            return valid
    return None


def run_cep_rules(con: sqlite3.Connection) -> list[dict]:
    """返回实际使用的 CEP 规则列表"""
    _sep("流程 0B：CEP 规则引擎（LLM 推导）")
    con.execute("DELETE FROM user_derived_events")
    con.commit()

    # 尝试 LLM 推导
    rules = _llm_derive_cep_rules(con)
    if rules:
        print(f"  [LLM] 推导出 {len(rules)} 条 CEP 规则")
        source = "LLM"
    else:
        print(f"  [FALLBACK] LLM 未返回，使用内置 {len(_BUILTIN_CEP_RULES)} 条 CEP 规则")
        rules = _BUILTIN_CEP_RULES
        source = "内置"

    baseline = con.execute("SELECT AVG(is_lead) FROM user_profile").fetchone()[0] or 0
    used_rules = []
    for rule in rules:
        name = rule.get("name", "")
        desc = rule.get("desc", "")
        sql  = rule.get("sql", "")
        try:
            con.execute(sql)
            con.commit()
            n = con.execute(
                "SELECT COUNT(DISTINCT user_id) FROM user_derived_events WHERE derived_event_type=?",
                (name,)
            ).fetchone()[0]
            if n == 0:
                print(f"  [{source}] {name:<28s} → 0 用户，跳过")
                continue
            lr = con.execute("""
                SELECT AVG(p.is_lead) FROM user_derived_events d
                JOIN user_profile p ON d.user_id=p.user_id WHERE d.derived_event_type=?
            """, (name,)).fetchone()[0] or 0
            tgi = lr / baseline * 100 if baseline > 0 else 0
            print(f"  [{source}] {name:<28s} {n:>8,} 用户  留资率={lr:.2%}  TGI={tgi:.0f}  {desc}")
            used_rules.append(rule)
        except Exception as e:
            print(f"  [{source}] {name:<28s} SQL执行失败: {e}")

    return used_rules

# ─────────────────────────────────────────────────────────────────────────────
# 流程 0C：人群规则引擎 → user_segments
# ─────────────────────────────────────────────────────────────────────────────

def run_segment_rules(con: sqlite3.Connection, cep_rules: list[dict]) -> list[dict]:
    """根据实际 CEP 规则自动生成 segment 规则"""
    _sep("流程 0C：人群规则引擎")
    con.execute("DELETE FROM user_segments")
    con.commit()

    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    baseline = con.execute("SELECT AVG(is_lead) FROM user_profile").fetchone()[0] or 0

    # 每个 CEP 规则对应一个 segment（名称由 LLM 在推导时提供 segment_name，否则自动生成）
    seg_rules = []
    for rule in cep_rules:
        name = rule.get("name", "")
        seg  = rule.get("segment_name") or name  # LLM 推导时可提供中文 segment 名
        desc = rule.get("desc", name)
        con.execute(
            "INSERT INTO user_segments(user_id,segment,segment_rule,derived_at)"
            f" SELECT DISTINCT user_id,?,?,? FROM user_derived_events WHERE derived_event_type=?",
            (seg, desc, now, name)
        )
        con.commit()
        n = con.execute("SELECT COUNT(*) FROM user_segments WHERE segment=?", (seg,)).fetchone()[0]
        lr = con.execute("""
            SELECT AVG(p.is_lead) FROM user_segments s
            JOIN user_profile p ON s.user_id=p.user_id WHERE s.segment=?
        """, (seg,)).fetchone()[0] or 0
        tgi = lr / baseline * 100 if baseline > 0 else 0
        print(f"  {seg:<20s}  {n:>8,} 人  留资率={lr:.2%}  TGI={tgi:.0f}")
        seg_rules.append({"segment": seg, "feature_event": name, "rule_desc": desc})

    return seg_rules

# ─────────────────────────────────────────────────────────────────────────────
# 流程 1：TBOX 本体初始化（Need/Item/Media 由 LLM 推导）
# ─────────────────────────────────────────────────────────────────────────────

_FALLBACK_NEED_ITEM_MEDIA = {
    "Need":  ["购车意向需求", "选车比价需求", "到店体验需求", "品牌偏好需求", "金融方案需求"],
    "Item":  ["新能源轿车", "新能源SUV", "豪华品牌车型", "国产新势力车型"],
    "Media": ["搜索结果广告", "车辆详情页广告", "地图导航广告", "信息流广告"],
}

def _llm_derive_need_item_media(con: sqlite3.Connection) -> dict | None:
    """让 LLM 根据数据中的品牌/车型分布推导 Need/Item/Media 节点"""
    # 收集已浏览的品牌/车型
    brand_rows = con.execute("""
        SELECT json_extract(attr_json,'$.brand') brand, COUNT(*) n
        FROM user_raw_events
        WHERE event_type IN ('search_vertical','search_general','view_car_detail')
          AND json_extract(attr_json,'$.brand') IS NOT NULL
        GROUP BY brand ORDER BY n DESC LIMIT 20
    """).fetchall()
    model_rows = con.execute("""
        SELECT json_extract(attr_json,'$.model') model, COUNT(*) n
        FROM user_raw_events
        WHERE event_type='view_car_detail'
          AND json_extract(attr_json,'$.model') IS NOT NULL
        GROUP BY model ORDER BY n DESC LIMIT 15
    """).fetchall()
    seg_rows = con.execute("""
        SELECT s.segment, AVG(p.is_lead) lr
        FROM user_segments s JOIN user_profile p ON s.user_id=p.user_id
        GROUP BY s.segment ORDER BY lr DESC
    """).fetchall()

    brand_summary = ", ".join(f"{r[0]}({r[1]:,}次)" for r in brand_rows)
    model_summary = ", ".join(f"{r[0]}({r[1]:,}次)" for r in model_rows)
    seg_summary   = "\n".join(f"  {r[0]}: 留资率={r[1]:.2%}" for r in seg_rows)

    prompt = f"""你是汽车营销本体专家。请根据以下用户行为数据，推导本体中 Need（需求）、Item（产品）、Media（媒介）节点。

【用户搜索/浏览的主要品牌（Top20）】
{brand_summary}

【用户浏览的主要车型（Top15）】
{model_summary}

【当前人群分层及留资率】
{seg_summary}

【要求】
1. Need：推导 4~6 个用户购车决策中的核心需求类型（抽象层面，非具体品牌）
2. Item：推导 4~6 个产品品类节点（基于真实品牌/车型聚类，而非品牌名本身）
3. Media：推导 3~5 个广告投放媒介节点（结合购车决策场景）
4. 节点名称使用中文，简洁明了

返回 JSON 对象，格式：
{{"Need": ["需求1","需求2",...], "Item": ["品类1","品类2",...], "Media": ["媒介1","媒介2",...]}}

只返回 JSON。"""

    raw = _llm_call(prompt)
    if not raw:
        return None
    result = _parse_json_block(raw)
    if isinstance(result, dict) and "Need" in result:
        return result
    return None


def init_tbox(G: nx.DiGraph, con: sqlite3.Connection) -> None:
    _sep("流程 1：TBOX 本体初始化")
    baseline = con.execute("SELECT AVG(is_lead) FROM user_profile").fetchone()[0] or 0

    # User 节点：数据驱动
    segs = con.execute("SELECT segment, segment_rule, COUNT(*) FROM user_segments GROUP BY segment").fetchall()
    for seg, rule, cnt in segs:
        lr = con.execute("""SELECT AVG(p.is_lead) FROM user_segments s
            JOIN user_profile p ON s.user_id=p.user_id WHERE s.segment=?""", (seg,)).fetchone()[0] or 0
        tgi = lr / baseline * 100 if baseline > 0 else 0
        add_node(G, seg, "User", segment_rule=rule, user_count=cnt, lead_rate=round(lr,4), tgi=round(tgi,1))
        print(f"  [User ] {seg:<20s} {cnt:>8,} 人  留资率={lr:.2%}  TGI={tgi:.0f}")

    # Event 节点：数据驱动
    evts = con.execute("""SELECT derived_event_type, source_rule, COUNT(DISTINCT user_id)
        FROM user_derived_events GROUP BY derived_event_type""").fetchall()
    for det, rule, cnt in evts:
        add_node(G, det, "Event", source_rule=rule, user_count=cnt)
        print(f"  [Event] {det:<28s} {cnt:>8,} 用户")

    # Need/Item/Media：LLM 推导，失败则用内置
    nim = _llm_derive_need_item_media(con)
    if nim:
        print("  [LLM] 推导 Need/Item/Media 节点")
        source = "LLM"
    else:
        print("  [FALLBACK] 使用内置 Need/Item/Media 节点")
        nim = _FALLBACK_NEED_ITEM_MEDIA
        source = "内置"

    for ntype in ["Need", "Item", "Media"]:
        for name in nim.get(ntype, []):
            if name not in G.nodes:
                add_node(G, name, ntype)
        names = [n for n, d in G.nodes(data=True) if d["node_type"] == ntype]
        print(f"  [{ntype:<5s}][{source}] {', '.join(names)}")

    print(f"\n  合法边类型: {list(VALID_EDGES.keys())}")

# ─────────────────────────────────────────────────────────────────────────────
# 流程 2：多轮 LLM 假设生成（螺旋 A）
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
    causal_check: str = ""   # 因果检验结果


def _build_hypothesis_prompt(G: nx.DiGraph, con: sqlite3.Connection,
                              already_confirmed: list[Hypothesis],
                              round_num: int, feedback: str = "") -> str:
    baseline = con.execute("SELECT AVG(is_lead) FROM user_profile").fetchone()[0] or 0
    seg_rows = con.execute("""
        SELECT s.segment, COUNT(*) n, AVG(p.is_lead) lr
        FROM user_segments s JOIN user_profile p ON s.user_id=p.user_id
        GROUP BY s.segment ORDER BY lr DESC
    """).fetchall()
    evt_rows = con.execute("""
        SELECT d.derived_event_type, COUNT(DISTINCT d.user_id) n, AVG(p.is_lead) lr
        FROM user_derived_events d JOIN user_profile p ON d.user_id=p.user_id
        GROUP BY d.derived_event_type ORDER BY lr DESC
    """).fetchall()

    seg_summary = "\n".join(
        f"  {r[0]}: {r[1]:,}人  留资率={r[2]:.2%}  TGI={r[2]/baseline*100:.0f}" for r in seg_rows)
    evt_summary = "\n".join(
        f"  {r[0]}: {r[1]:,}用户  留资率={r[2]:.2%}  TGI={r[2]/baseline*100:.0f}" for r in evt_rows)

    confirmed_str = ""
    if already_confirmed:
        lines = [f"  {h.source_node} --[{h.edge_type}]--> {h.target_node} (TGI={h.tgi:.0f})"
                 for h in already_confirmed]
        confirmed_str = f"\n【第{round_num-1}轮已确权路径（勿重复）】\n" + "\n".join(lines)

    feedback_str = f"\n【上轮反馈（请据此换视角）】\n{feedback}" if feedback else ""

    return f"""你是汽车营销数据挖掘专家，目标是识别有购车留资意向的用户（留资=提交购车询价）。
这是第 {round_num} 轮推理，请提出新的关系假设路径。

{_ontology_ctx(G)}

【人群分层（含留资率TGI）】
{seg_summary}

【衍生事件（含留资率TGI）】
{evt_summary}

【全量留资基线】{baseline:.2%}
{confirmed_str}
{feedback_str}

【本轮要求】
1. 提出 5 条新的假设，优先探索尚未确权的路径和视角
2. 避免把相关性误认为因果——请在 causal_reasoning 字段说明为什么是因果而非相关
   （例：游泳和冰淇淋销量相关，但原因都是夏天，不是因果）
3. 对于 Triggers_Need（Event→Need）类假设，需说明：
   a) 该事件在时序上是否先于留资（时序检验）
   b) 排除混淆变量的理由（为什么不是第三个变量同时导致了事件和需求）
4. source_node/target_node 必须是图谱中已存在的节点名称
5. edge_type 必须合法

返回 JSON 数组，每条含：
  id, description, source_node, target_node, edge_type,
  target_segment, feature_event, causal_reasoning

只返回 JSON。"""


def generate_hypotheses_multi_round(
    G: nx.DiGraph, con: sqlite3.Connection
) -> tuple[list[Hypothesis], list[Hypothesis]]:
    """
    多轮假设生成，返回 (全部假设列表, 确权假设列表)
    每轮最多生成5条，TGI不达标时换视角重试，最多 MAX_ROUNDS 轮
    """
    all_hypotheses: list[Hypothesis] = []
    all_confirmed: list[Hypothesis] = []
    feedback = ""

    for rnd in range(1, MAX_ROUNDS + 1):
        _sep(f"流程 2+3：第 {rnd} 轮假设生成 + TGI 验证")

        prompt = _build_hypothesis_prompt(G, con, all_confirmed, rnd, feedback)
        raw = _llm_call(prompt)
        raw_list: list[dict] = []
        if raw:
            result = _parse_json_block(raw)
            if isinstance(result, list):
                raw_list = result
                print(f"  [LLM] 第{rnd}轮 生成 {len(raw_list)} 条假设")

        if not raw_list:
            print(f"  [FALLBACK] LLM 无响应，使用内置假设（仅第1轮）")
            if rnd == 1:
                raw_list = _FALLBACK_HYPOTHESES
            else:
                break

        # 本轮 TGI 验证
        round_confirmed = []
        low_tgi_feedback = []
        for i, h_dict in enumerate(raw_list):
            hyp = Hypothesis(
                id=h_dict.get("id") or f"R{rnd}H{i+1}",
                description=h_dict.get("description", ""),
                source_node=h_dict.get("source_node", ""),
                target_node=h_dict.get("target_node", ""),
                edge_type=h_dict.get("edge_type", ""),
                target_segment=h_dict.get("target_segment", ""),
                feature_event=h_dict.get("feature_event", ""),
                causal_check=h_dict.get("causal_reasoning", ""),
                source="llm" if raw else "fallback",
            )
            all_hypotheses.append(hyp)

            # 节点/segment 存在性检查
            if hyp.source_node not in G.nodes:
                print(f"  [{hyp.id}] ⚠  source_node 不存在: {hyp.source_node}")
                low_tgi_feedback.append(f"{hyp.id}: source_node={hyp.source_node!r} 不在图谱")
                continue
            if hyp.target_node not in G.nodes:
                print(f"  [{hyp.id}] ⚠  target_node 不存在: {hyp.target_node}")
                low_tgi_feedback.append(f"{hyp.id}: target_node={hyp.target_node!r} 不在图谱")
                continue
            if not con.execute("SELECT 1 FROM user_segments WHERE segment=? LIMIT 1",
                               (hyp.target_segment,)).fetchone():
                print(f"  [{hyp.id}] ⚠  segment 不存在: {hyp.target_segment}")
                low_tgi_feedback.append(f"{hyp.id}: segment={hyp.target_segment!r} 不存在")
                continue

            # TGI 计算
            hyp.tgi = round(_compute_tgi(con, hyp.target_segment, hyp.feature_event), 1)
            hyp.confirmed = hyp.tgi >= TGI_THRESHOLD
            status = "✅ 确权" if hyp.confirmed else "❌ 未达标"
            print(f"  [{hyp.id}] TGI={hyp.tgi:6.1f}  {status}  {hyp.description}")
            if hyp.causal_check:
                print(f"           因果推理: {hyp.causal_check[:80]}")

            if hyp.confirmed:
                # 因果检验（时序 + 混淆变量提示）
                causal_warning = _causal_check(con, hyp)
                if causal_warning:
                    print(f"           ⚠ 因果警告: {causal_warning}")
                    hyp.causal_check += f" | 系统警告: {causal_warning}"
                try:
                    add_edge(G, hyp.source_node, hyp.target_node, hyp.edge_type,
                             tgi=hyp.tgi, hypothesis_id=hyp.id)
                    print(f"           → 写入图谱: {hyp.source_node} --[{hyp.edge_type}]--> {hyp.target_node}")
                    round_confirmed.append(hyp)
                    all_confirmed.append(hyp)
                except ValueError as e:
                    print(f"           ⚠ 合规校验失败: {e}")
            else:
                low_tgi_feedback.append(
                    f"{hyp.id}(TGI={hyp.tgi:.0f}): {hyp.description[:40]} — TGI 低于{TGI_THRESHOLD}")

        print(f"\n  第{rnd}轮确权: {len(round_confirmed)} 条，累计确权: {len(all_confirmed)} 条")

        if len(all_confirmed) >= MIN_CONFIRMED:
            print(f"  ✅ 已达到最低确权数 {MIN_CONFIRMED}，停止迭代")
            break

        if rnd < MAX_ROUNDS:
            feedback = "上轮未确权原因:\n" + "\n".join(f"  - {f}" for f in low_tgi_feedback)
            feedback += f"\n\n请换视角，探索其他人群-事件-需求组合，避免重复上轮路径。"
            print(f"  🔄 TGI 达标不足，进入第 {rnd+1} 轮，调整视角...")

    print(f"\n  图谱节点数: {G.number_of_nodes()}，总确权边数: {G.number_of_edges()}")
    return all_hypotheses, all_confirmed

# ─────────────────────────────────────────────────────────────────────────────
# 因果检验（时序 + 留资率对照）
# ─────────────────────────────────────────────────────────────────────────────

def _causal_check(con: sqlite3.Connection, h: Hypothesis) -> str:
    """
    对 Triggers_Need（Event→Need）类假设做简单因果检验：
    1. 有该衍生事件的用户 vs 无该事件的用户，留资率差异是否显著
    2. 控制变量检验：在同一人群（segment）内，有/无事件的留资率差
    返回警告字符串（空字符串=无警告）
    """
    if h.edge_type != "Triggers_Need":
        return ""

    feat = h.feature_event
    seg  = h.target_segment

    # 有该事件的用户留资率
    lr_with = con.execute("""
        SELECT AVG(p.is_lead) FROM user_profile p
        WHERE EXISTS (SELECT 1 FROM user_derived_events d
                      WHERE d.user_id=p.user_id AND d.derived_event_type=?)
    """, (feat,)).fetchone()[0] or 0

    # 无该事件的用户留资率
    lr_without = con.execute("""
        SELECT AVG(p.is_lead) FROM user_profile p
        WHERE NOT EXISTS (SELECT 1 FROM user_derived_events d
                          WHERE d.user_id=p.user_id AND d.derived_event_type=?)
    """, (feat,)).fetchone()[0] or 0

    # 差异检验：若有/无事件的留资率差 < 5%，可能是伪相关
    diff = lr_with - lr_without
    if diff < 0.05:
        return (f"有{feat}事件留资率={lr_with:.2%} vs 无={lr_without:.2%}，"
                f"差异仅{diff:.2%}，因果效应弱，注意排除混淆变量")

    # 在 segment 内检验（控制 segment 变量）
    lr_seg_with = con.execute("""
        SELECT AVG(p.is_lead) FROM user_segments s
        JOIN user_profile p ON s.user_id=p.user_id
        WHERE s.segment=?
          AND EXISTS (SELECT 1 FROM user_derived_events d
                      WHERE d.user_id=s.user_id AND d.derived_event_type=?)
    """, (seg, feat)).fetchone()[0] or 0

    lr_seg_without = con.execute("""
        SELECT AVG(p.is_lead) FROM user_segments s
        JOIN user_profile p ON s.user_id=p.user_id
        WHERE s.segment=?
          AND NOT EXISTS (SELECT 1 FROM user_derived_events d
                          WHERE d.user_id=s.user_id AND d.derived_event_type=?)
    """, (seg, feat)).fetchone()[0] or 0

    seg_diff = lr_seg_with - lr_seg_without
    if seg_diff < 0.03 and lr_seg_without > 0:
        return (f"在{seg}内，有/无{feat}的留资率差仅{seg_diff:.2%}，"
                f"控制人群变量后效应消失，该关系可能为相关性非因果")

    return ""

# ─────────────────────────────────────────────────────────────────────────────
# TGI 计算
# ─────────────────────────────────────────────────────────────────────────────

def _compute_tgi(con: sqlite3.Connection, target_segment: str, feature_event: str) -> float:
    baseline = con.execute("SELECT AVG(is_lead) FROM user_profile").fetchone()[0] or 0
    if baseline == 0:
        return 0.0
    lr = con.execute("""
        SELECT AVG(p.is_lead)
        FROM user_segments s
        JOIN user_derived_events d ON s.user_id=d.user_id AND d.derived_event_type=?
        JOIN user_profile p ON s.user_id=p.user_id
        WHERE s.segment=?
    """, (feature_event, target_segment)).fetchone()[0] or 0
    return (lr / baseline) * 100

# ─────────────────────────────────────────────────────────────────────────────
# 流程 4：LLM 营销策略生成
# ─────────────────────────────────────────────────────────────────────────────

def generate_strategies(confirmed: list[Hypothesis], G: nx.DiGraph, con: sqlite3.Connection) -> None:
    _sep("流程 4：LLM 营销策略生成")
    if not confirmed:
        print("  无确权假设，跳过")
        return

    baseline = con.execute("SELECT AVG(is_lead) FROM user_profile").fetchone()[0] or 0
    edge_lines = []
    for h in confirmed:
        n  = con.execute("SELECT COUNT(*) FROM user_segments WHERE segment=?", (h.target_segment,)).fetchone()[0]
        lr = con.execute("""SELECT AVG(p.is_lead) FROM user_segments s
            JOIN user_profile p ON s.user_id=p.user_id WHERE s.segment=?""",
            (h.target_segment,)).fetchone()[0] or 0
        causal_note = f"  因果注: {h.causal_check[:60]}" if h.causal_check else ""
        edge_lines.append(
            f"  {h.source_node} --[{h.edge_type}]--> {h.target_node}"
            f"  (TGI={h.tgi:.0f}, 人群={n:,}人, 留资率={lr:.2%}){causal_note}"
        )

    prompt = f"""你是汽车营销策略专家，目标是触达有购车留资意向的用户。

{_ontology_ctx(G)}

【已确权图谱边（TGI≥{TGI_THRESHOLD}，已通过因果检验）】
{chr(10).join(edge_lines)}

【全量留资基线】{baseline:.2%}

为每条确权路径生成营销策略，JSON 数组，每条含：
segment_name, insight, need_path, ad_channel, ad_creative,
budget_priority（P0/P1/P2+理由）, explainability

只返回 JSON。"""

    raw = _llm_call(prompt)
    strategies = []
    if raw:
        result = _parse_json_block(raw)
        if isinstance(result, list):
            strategies = result
            print(f"  [LLM] 生成 {len(strategies)} 条策略\n")

    if not strategies:
        print("  [FALLBACK] 基础策略\n")
        for h in confirmed:
            n  = con.execute("SELECT COUNT(*) FROM user_segments WHERE segment=?", (h.target_segment,)).fetchone()[0]
            lr = con.execute("""SELECT AVG(p.is_lead) FROM user_segments s
                JOIN user_profile p ON s.user_id=p.user_id WHERE s.segment=?""",
                (h.target_segment,)).fetchone()[0] or 0
            strategies.append({
                "segment_name":   h.target_segment,
                "insight":        f"具有 {h.feature_event} 行为，留资率={lr:.2%}",
                "need_path":      f"{h.source_node} → {h.target_node}",
                "ad_channel":     "搜索结果广告",
                "ad_creative":    "结合品牌/车型，突出金融方案或到店优惠",
                "budget_priority": f"P{'0' if h.tgi >= 150 else '1'}",
                "explainability": f"TGI={h.tgi:.0f}，人群={n:,}人，基线={baseline:.2%}",
            })

    for s in strategies:
        print(f"## {s.get('segment_name','')}")
        print(f"  洞察: {s.get('insight','')}")
        print(f"  链路: {s.get('need_path','')}")
        print(f"  渠道: {s.get('ad_channel','')}")
        print(f"  创意: {s.get('ad_creative','')}")
        print(f"  预算: {s.get('budget_priority','')}")
        print(f"  解释: {s.get('explainability','')}\n")

# ─────────────────────────────────────────────────────────────────────────────
# 模拟数据（无真实文件时的 fallback）
# ─────────────────────────────────────────────────────────────────────────────

def _gen_simulated_records(n_pos=500, n_neg=500):
    _BRANDS = ["比亚迪","理想","蔚来","小鹏","华为问界"]
    _CITIES = [("北京","一线"),("上海","一线"),("武汉","新一线"),("成都","新一线"),("郑州","二线")]
    _AGES   = ["18-24岁","24-34岁","35-44岁","45-54岁"]
    def _tag(city, tier, age):
        return (f"年龄段:{age}#性别:{'男性' if random.random()>0.4 else '女性'}"
                f"#城市:{city}#城市等级:{tier}#婚恋状态:{'已婚' if random.random()>0.5 else '未婚'}"
                f"#消费频率:{'较高频' if random.random()>0.5 else '中频'}#设备价格:5000~8000#房产:有房产")
    def _events(res_keys):
        base = datetime(2025, 12, 1)
        return [{"timestamp": (base+timedelta(days=random.randint(0,90),hours=random.randint(0,23))).strftime("%Y%m%d%H"),
                 "res_key": rk, "time_str": (base+timedelta(days=random.randint(0,90))).strftime("%Y%m%d"),
                 "dur_time": round(random.uniform(0,5000),2)} for rk in res_keys]
    _POS = ["搜索_三车垂媒_比亚迪{{ }}","搜索_泛资讯_无明确品牌{{ }}",
            "浏览_三车垂媒车辆详情_理想-L9{{SUV}}","浏览_三车垂媒车贷计算_蔚来-ET5{{}}",
            "路过门店","搜索_泛资讯_华为问界{{ }}","路过门店","留资_线下渠道"]
    _NEG = ["搜索_泛资讯_无明确品牌{{ }}","地图/打车软件使用","搜索_泛资讯_无明确品牌{{ }}"]
    pos = [{"user_id":f"pos_{i}","user_tag":_tag(*random.choice(_CITIES),random.choice(_AGES)),
             "user_events":_events(_POS+[f"搜索_泛资讯_{random.choice(_BRANDS)}{{{{ }}}}" for _ in range(random.randint(0,3))])}
           for i in range(n_pos)]
    neg = [{"user_id":f"neg_{i}","user_tag":_tag(*random.choice(_CITIES),random.choice(_AGES)),
             "user_events":_events(_NEG+["搜索_泛资讯_无明确品牌{{ }}" for _ in range(random.randint(0,2))])}
           for i in range(n_neg)]
    return pos, neg

# ─────────────────────────────────────────────────────────────────────────────
# 内置 fallback 假设
# ─────────────────────────────────────────────────────────────────────────────

_FALLBACK_HYPOTHESES: list[dict] = [
    {"id":"H1","source":"fallback","description":"持续搜索型用户具有多日搜索衍生事件",
     "source_node":"持续搜索型用户","target_node":"multi_day_search",
     "edge_type":"Has_Recent_Event","target_segment":"持续搜索型用户",
     "feature_event":"multi_day_search","causal_reasoning":"该用户本身就是由 multi_day_search 定义的，定义上直接对应"},
    {"id":"H2","source":"fallback","description":"多日搜索触发购车意向需求",
     "source_node":"multi_day_search","target_node":"购车意向需求",
     "edge_type":"Triggers_Need","target_segment":"持续搜索型用户",
     "feature_event":"multi_day_search","causal_reasoning":"持续搜索是主动信息收集行为，时序上先于留资，排除偶发性"},
    {"id":"H3","source":"fallback","description":"深度比价型用户具有详情+贷款双重浏览",
     "source_node":"深度比价型用户","target_node":"detail_view_with_loan",
     "edge_type":"Has_Recent_Event","target_segment":"深度比价型用户",
     "feature_event":"detail_view_with_loan","causal_reasoning":"定义直接对应"},
    {"id":"H4","source":"fallback","description":"详情+贷款浏览触发金融方案需求",
     "source_node":"detail_view_with_loan","target_node":"金融方案需求",
     "edge_type":"Triggers_Need","target_segment":"深度比价型用户",
     "feature_event":"detail_view_with_loan","causal_reasoning":"查看贷款是明确的金融需求探索行为，时序先于留资"},
    {"id":"H5","source":"fallback","description":"到店意向型用户具有高强度路过门店事件",
     "source_node":"到店意向型用户","target_node":"pass_dealership_intent",
     "edge_type":"Has_Recent_Event","target_segment":"到店意向型用户",
     "feature_event":"pass_dealership_intent","causal_reasoning":"定义直接对应"},
]

# ─────────────────────────────────────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="双螺旋确权 POC v4 — 留资线索人群挖掘")
    ap.add_argument("--positive",     default=None,  help="正样本 JSON 文件路径")
    ap.add_argument("--negative",     default=None,  help="负样本 JSON 文件路径")
    ap.add_argument("--reset",        action="store_true", help="重新初始化数据库（重新导入数据）")
    ap.add_argument("--dump-unknown", action="store_true", help="打印未识别的 res_key 事件类型")
    args = ap.parse_args()

    if args.reset:
        print("[--reset] 将重新初始化数据库，清空所有已有数据")

    _sep("双螺旋确权 POC v4 — 留资线索人群挖掘")
    print("三层流水线: 原始事件(res_key) → LLM推导CEP → 人群分层 → TBOX → 多轮LLM假设 → 策略")

    con = sqlite3.connect(":memory:")
    G   = nx.DiGraph()

    build_raw_data(con, args.positive, args.negative, dump_unknown=args.dump_unknown)
    if args.dump_unknown:
        return  # dump-unknown 模式只打印，不继续后续流程

    cep_rules  = run_cep_rules(con)
    seg_rules  = run_segment_rules(con, cep_rules)
    init_tbox(G, con)
    all_hyps, confirmed = generate_hypotheses_multi_round(G, con)
    generate_strategies(confirmed, G, con)

    _sep("POC 运行完毕")
    print(f"  总假设数: {len(all_hyps)}，确权: {len(confirmed)}")
    print(f"  TBOX 图谱边数: {G.number_of_edges()}")
    _sep()


if __name__ == "__main__":
    main()
