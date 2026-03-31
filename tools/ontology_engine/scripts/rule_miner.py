#!/usr/bin/env python3
"""
rule_miner.py — 规则挖掘模块（训练集）
======================================

职责：
  1. 调用 data_loader.load() 加载训练数据
  2. CEP 规则引擎 → user_derived_events
  3. 人群规则引擎 → user_segments
  4. TBOX 本体初始化（数据驱动）
  5. LLM 假设生成（螺旋A）
  6. ABOX TGI 验证 + 算力确权（螺旋B）
  7. LLM 营销策略生成
  8. 将确权规则写出到 confirmed_rules.json（供 rule_validator.py 复用）
  9. 将本体图谱增量合并到 ontology.json（跨批次持续丰富）

用法：
    python3 scripts/rule_miner.py --positive data/positive.json --negative data/negative.json
    python3 scripts/rule_miner.py --positive data/pos2.json --negative data/neg2.json  # 第二批，增量合并
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any

import networkx as nx

from data_loader import load

# ─────────────────────────────────────────────────────────────────────────────
# Meta-Ontology 规范（严格白名单）
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

# 输出文件（相对于脚本目录）
_SCRIPT_DIR      = os.path.dirname(os.path.abspath(__file__))
CONFIRMED_RULES  = os.path.join(_SCRIPT_DIR, "confirmed_rules.json")
ONTOLOGY_FILE    = os.path.join(_SCRIPT_DIR, "ontology.json")
LLM_CONFIG_PATH  = os.path.join(_SCRIPT_DIR, "llm_config.json")


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
        raise ValueError(f"{edge_type}: src 类型 {st!r} 不合法，需为 {ok_s}")
    if dt not in ok_d:
        raise ValueError(f"{edge_type}: dst 类型 {dt!r} 不合法，需为 {ok_d}")
    G.add_edge(src, dst, edge_type=edge_type, **attrs)


# ─────────────────────────────────────────────────────────────────────────────
# 流程 0B：CEP 规则引擎 → user_derived_events
# ─────────────────────────────────────────────────────────────────────────────

CEP_RULES = [
    (
        "multi_day_search",
        "R1: 搜索行为跨越>=3个不同日期",
        """
        INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
        SELECT user_id, MAX(event_time), 'multi_day_search',
               'R1: 搜索行为跨越>=3个不同日期',
               json_object('search_days', COUNT(DISTINCT time_str), 'total_count', COUNT(*))
        FROM user_raw_events
        WHERE event_type IN ('search_vertical','search_general')
        GROUP BY user_id HAVING COUNT(DISTINCT time_str) >= 3
        """,
    ),
    (
        "brand_focused_search",
        "R2: 有明确品牌的搜索>=2次",
        """
        INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
        SELECT user_id, MAX(event_time), 'brand_focused_search',
               'R2: 有明确品牌的搜索>=2次',
               json_object('count', COUNT(*),
                           'brands', GROUP_CONCAT(DISTINCT json_extract(attr_json,'$.brand')))
        FROM user_raw_events
        WHERE event_type IN ('search_vertical','search_general')
          AND json_extract(attr_json,'$.brand') IS NOT NULL
        GROUP BY user_id HAVING COUNT(*) >= 2
        """,
    ),
    (
        "detail_view_with_loan",
        "R3: 同时浏览车辆详情页且浏览车贷计算页",
        """
        INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
        SELECT user_id, MAX(event_time), 'detail_view_with_loan',
               'R3: 同时浏览车辆详情页且浏览车贷计算页',
               json_object('detail_count', SUM(event_type='view_car_detail'),
                           'loan_count',   SUM(event_type='view_loan_calc'))
        FROM user_raw_events
        WHERE event_type IN ('view_car_detail','view_loan_calc')
        GROUP BY user_id
        HAVING SUM(event_type='view_car_detail') >= 1
           AND SUM(event_type='view_loan_calc')   >= 1
        """,
    ),
    (
        "pass_dealership_intent",
        "R4: 路过门店>=2次，或1次停留>1800s",
        """
        INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
        SELECT user_id, MAX(event_time), 'pass_dealership_intent',
               'R4: 路过门店>=2次，或1次停留>1800s',
               json_object('count', COUNT(*), 'max_dur', MAX(dur_time))
        FROM user_raw_events
        WHERE event_type = 'pass_dealership'
        GROUP BY user_id HAVING COUNT(*) >= 2 OR MAX(dur_time) > 1800
        """,
    ),
    (
        "high_engagement_search",
        "R5: 单次搜索停留>=3000秒",
        """
        INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
        SELECT user_id, MAX(event_time), 'high_engagement_search',
               'R5: 单次搜索停留>=3000秒',
               json_object('max_dur', MAX(dur_time), 'count', COUNT(*))
        FROM user_raw_events
        WHERE event_type = 'search_general' AND dur_time >= 3000
        GROUP BY user_id
        """,
    ),
]


def run_cep_rules(con: sqlite3.Connection) -> None:
    _sep("流程 0B：CEP 规则引擎")
    con.execute("""
        CREATE TABLE IF NOT EXISTS user_derived_events (
            event_id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id            TEXT,
            event_time         TEXT,
            derived_event_type TEXT,
            source_rule        TEXT,
            attr_json          TEXT
        )
    """)
    con.execute("DELETE FROM user_derived_events")
    con.commit()

    baseline = con.execute("SELECT AVG(is_lead) FROM user_profile").fetchone()[0] or 0
    for det, desc, sql in CEP_RULES:
        con.execute(sql)
        con.commit()
        n = con.execute(
            "SELECT COUNT(DISTINCT user_id) FROM user_derived_events WHERE derived_event_type=?",
            (det,)
        ).fetchone()[0]
        lr = con.execute("""
            SELECT AVG(p.is_lead) FROM user_derived_events d
            JOIN user_profile p ON d.user_id=p.user_id
            WHERE d.derived_event_type=?
        """, (det,)).fetchone()[0] or 0
        tgi = lr / baseline * 100 if baseline > 0 else 0
        print(f"  {det:<28s} {n:>6,} 用户  留资率={lr:.2%}  TGI={tgi:.0f}  [{desc}]")


# ─────────────────────────────────────────────────────────────────────────────
# 流程 0C：人群规则引擎 → user_segments
# ─────────────────────────────────────────────────────────────────────────────

SEGMENT_RULES = [
    {
        "segment":   "持续搜索型用户",
        "rule_desc": "跨>=3天持续搜索",
        "sql":       "SELECT DISTINCT user_id FROM user_derived_events WHERE derived_event_type='multi_day_search'",
    },
    {
        "segment":   "品牌意向型用户",
        "rule_desc": "有明确品牌搜索>=2次",
        "sql":       "SELECT DISTINCT user_id FROM user_derived_events WHERE derived_event_type='brand_focused_search'",
    },
    {
        "segment":   "深度比价型用户",
        "rule_desc": "同时浏览详情页+车贷计算页",
        "sql":       "SELECT DISTINCT user_id FROM user_derived_events WHERE derived_event_type='detail_view_with_loan'",
    },
    {
        "segment":   "到店意向型用户",
        "rule_desc": "高强度路过门店",
        "sql":       "SELECT DISTINCT user_id FROM user_derived_events WHERE derived_event_type='pass_dealership_intent'",
    },
    {
        "segment":   "高投入搜索型用户",
        "rule_desc": "单次搜索停留>=3000s",
        "sql":       "SELECT DISTINCT user_id FROM user_derived_events WHERE derived_event_type='high_engagement_search'",
    },
]


def run_segment_rules(con: sqlite3.Connection) -> None:
    _sep("流程 0C：人群规则引擎")
    con.execute("""
        CREATE TABLE IF NOT EXISTS user_segments (
            user_id TEXT, segment TEXT, segment_rule TEXT, derived_at TEXT
        )
    """)
    con.execute("DELETE FROM user_segments")
    con.commit()

    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    baseline = con.execute("SELECT AVG(is_lead) FROM user_profile").fetchone()[0] or 0
    for sr in SEGMENT_RULES:
        con.execute(
            f"INSERT INTO user_segments(user_id,segment,segment_rule,derived_at)"
            f" SELECT user_id,?,?,? FROM ({sr['sql']})",
            (sr["segment"], sr["rule_desc"], now),
        )
    con.commit()

    for sr in SEGMENT_RULES:
        n = con.execute(
            "SELECT COUNT(*) FROM user_segments WHERE segment=?", (sr["segment"],)
        ).fetchone()[0]
        lr = con.execute("""
            SELECT AVG(p.is_lead) FROM user_segments s
            JOIN user_profile p ON s.user_id=p.user_id WHERE s.segment=?
        """, (sr["segment"],)).fetchone()[0] or 0
        tgi = lr / baseline * 100 if baseline > 0 else 0
        print(f"  {sr['segment']:<14s}  {n:>6,} 人  留资率={lr:.2%}  TGI={tgi:.0f}")


# ─────────────────────────────────────────────────────────────────────────────
# 流程 1：TBOX 本体初始化 + 增量合并
# ─────────────────────────────────────────────────────────────────────────────

_PRESET_NODES: list[tuple[str, str]] = [
    ("购车意向需求",   "Need"),
    ("选车比价需求",   "Need"),
    ("到店体验需求",   "Need"),
    ("品牌偏好需求",   "Need"),
    ("金融方案需求",   "Need"),
    ("新能源轿车",     "Item"),
    ("新能源SUV",      "Item"),
    ("豪华品牌车型",   "Item"),
    ("国产新势力车型", "Item"),
    ("搜索结果广告",   "Media"),
    ("车辆详情页广告", "Media"),
    ("地图导航广告",   "Media"),
    ("信息流广告",     "Media"),
]


def _load_ontology() -> dict:
    """从 ontology.json 读取已有图谱数据，不存在则返回空结构"""
    if os.path.exists(ONTOLOGY_FILE):
        with open(ONTOLOGY_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"nodes": {}, "edges": []}


def _save_ontology(data: dict) -> None:
    with open(ONTOLOGY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def init_tbox(G: nx.DiGraph, con: sqlite3.Connection) -> None:
    _sep("流程 1：TBOX 本体初始化（增量合并）")
    baseline = con.execute("SELECT AVG(is_lead) FROM user_profile").fetchone()[0] or 0

    # 先加载已有本体（跨批次持久化）
    existing = _load_ontology()
    for name, attrs in existing["nodes"].items():
        try:
            add_node(G, name, attrs["node_type"], **{k: v for k, v in attrs.items() if k != "node_type"})
        except ValueError:
            pass
    for e in existing["edges"]:
        try:
            add_edge(G, e["src"], e["dst"], e["edge_type"],
                     **{k: v for k, v in e.items() if k not in ("src", "dst", "edge_type")})
        except (ValueError, KeyError):
            pass

    # 本批次 User 节点（数据驱动）
    segs = con.execute(
        "SELECT segment, segment_rule, COUNT(*) FROM user_segments GROUP BY segment"
    ).fetchall()
    for seg, rule, cnt in segs:
        lr = con.execute("""
            SELECT AVG(p.is_lead) FROM user_segments s
            JOIN user_profile p ON s.user_id=p.user_id WHERE s.segment=?
        """, (seg,)).fetchone()[0] or 0
        tgi = lr / baseline * 100 if baseline > 0 else 0
        add_node(G, seg, "User", segment_rule=rule, user_count=cnt,
                 lead_rate=round(lr, 4), tgi=round(tgi, 1))
        print(f"  [User ] {seg:<16s} {cnt:>6,} 人  留资率={lr:.2%}  TGI={tgi:.0f}")

    # 本批次 Event 节点（数据驱动）
    evts = con.execute("""
        SELECT derived_event_type, source_rule, COUNT(DISTINCT user_id)
        FROM user_derived_events GROUP BY derived_event_type
    """).fetchall()
    for det, rule, cnt in evts:
        add_node(G, det, "Event", source_rule=rule, user_count=cnt)
        print(f"  [Event] {det:<28s} {cnt:>6,} 用户")

    # 预定义节点（Need/Item/Media）
    for name, ntype in _PRESET_NODES:
        if name not in G.nodes:
            add_node(G, name, ntype)

    need_names  = [n for n, d in G.nodes(data=True) if d["node_type"] == "Need"]
    item_names  = [n for n, d in G.nodes(data=True) if d["node_type"] == "Item"]
    media_names = [n for n, d in G.nodes(data=True) if d["node_type"] == "Media"]
    print(f"\n  [Need ] {', '.join(need_names)}")
    print(f"  [Item ] {', '.join(item_names)}")
    print(f"  [Media] {', '.join(media_names)}")


# ─────────────────────────────────────────────────────────────────────────────
# LLM 工具函数
# ─────────────────────────────────────────────────────────────────────────────

_LLM_CFG: dict | None = None


def _llm_call(prompt: str) -> str | None:
    global _LLM_CFG
    if _LLM_CFG is None and os.path.exists(LLM_CONFIG_PATH):
        with open(LLM_CONFIG_PATH, encoding="utf-8") as f:
            _LLM_CFG = json.load(f)
    if not _LLM_CFG or not _LLM_CFG.get("api_key"):
        return None
    try:
        from openai import OpenAI
        client = OpenAI(api_key=_LLM_CFG["api_key"], base_url=_LLM_CFG["base_url"])
        resp = client.chat.completions.create(
            model=_LLM_CFG["model"],
            max_tokens=_LLM_CFG.get("max_tokens", 2048),
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content
    except Exception as e:
        print(f"  [LLM] 调用失败: {e}")
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
# 流程 2：LLM 假设生成（螺旋 A）
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
    {"id": "H1", "source": "fallback",
     "description": "持续搜索型用户具有多日搜索衍生事件",
     "source_node": "持续搜索型用户", "target_node": "multi_day_search",
     "edge_type": "Has_Recent_Event",
     "target_segment": "持续搜索型用户", "feature_event": "multi_day_search"},
    {"id": "H2", "source": "fallback",
     "description": "多日搜索触发购车意向需求",
     "source_node": "multi_day_search", "target_node": "购车意向需求",
     "edge_type": "Triggers_Need",
     "target_segment": "持续搜索型用户", "feature_event": "multi_day_search"},
    {"id": "H3", "source": "fallback",
     "description": "深度比价型用户具有详情+贷款双重浏览事件",
     "source_node": "深度比价型用户", "target_node": "detail_view_with_loan",
     "edge_type": "Has_Recent_Event",
     "target_segment": "深度比价型用户", "feature_event": "detail_view_with_loan"},
    {"id": "H4", "source": "fallback",
     "description": "详情+贷款浏览触发金融方案需求",
     "source_node": "detail_view_with_loan", "target_node": "金融方案需求",
     "edge_type": "Triggers_Need",
     "target_segment": "深度比价型用户", "feature_event": "detail_view_with_loan"},
    {"id": "H5", "source": "fallback",
     "description": "到店意向型用户具有高强度路过门店事件",
     "source_node": "到店意向型用户", "target_node": "pass_dealership_intent",
     "edge_type": "Has_Recent_Event",
     "target_segment": "到店意向型用户", "feature_event": "pass_dealership_intent"},
]


def generate_hypotheses(G: nx.DiGraph, con: sqlite3.Connection) -> list[Hypothesis]:
    _sep("流程 2：LLM 假设生成（螺旋 A）")
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
        f"  {r[0]}: {r[1]:,}人  留资率={r[2]:.2%}  TGI={r[2]/baseline*100:.0f}" for r in seg_rows
    )
    evt_summary = "\n".join(
        f"  {r[0]}: {r[1]:,}用户  留资率={r[2]:.2%}  TGI={r[2]/baseline*100:.0f}" for r in evt_rows
    )

    prompt = f"""你是汽车营销数据挖掘专家，目标是挖掘有购车留资意向的用户。
请严格遵循本体规范，提出 5 条可用数据验证的关系挖掘假设。

{_ontology_ctx(G)}

【人群分层统计（含留资率TGI）】
{seg_summary}

【衍生事件统计（含留资率TGI）】
{evt_summary}

【全量留资基线】留资率={baseline:.2%}

约束：
1. source_node/target_node 必须是已列出的节点名称，不得新创
2. edge_type 必须是合法边类型之一
3. Has_Recent_Event 只能 User→Event；Triggers_Need 只能 Event→Need
4. target_segment 必须是人群分层中的 segment 值
5. feature_event 必须是衍生事件中的 derived_event_type 值
6. 优先选择 TGI>120 的路径

返回 JSON 数组，每条含：id, description, source_node, target_node, edge_type, target_segment, feature_event
只返回 JSON。"""

    raw = _llm_call(prompt)
    raw_list: list[dict] = []
    if raw:
        try:
            s, e = raw.find("["), raw.rfind("]") + 1
            raw_list = json.loads(raw[s:e])
            print(f"  [LLM] 生成 {len(raw_list)} 条假设")
        except Exception as ex:
            print(f"  [LLM] 解析失败: {ex}，使用 fallback")
    if not raw_list:
        print("  [FALLBACK] 使用内置假设")
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
# 流程 3：ABOX TGI 验证 + 算力确权（螺旋 B）
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


def validate_hypotheses(
    hypotheses: list[Hypothesis], con: sqlite3.Connection, G: nx.DiGraph
) -> list[Hypothesis]:
    _sep("流程 3：ABOX TGI 验证 + 算力确权（螺旋 B）")
    confirmed = []
    for h in hypotheses:
        if h.source_node not in G.nodes:
            print(f"  [{h.id}] ⚠  source_node 不存在: {h.source_node}")
            continue
        if h.target_node not in G.nodes:
            print(f"  [{h.id}] ⚠  target_node 不存在: {h.target_node}")
            continue
        if not con.execute(
            "SELECT 1 FROM user_segments WHERE segment=? LIMIT 1", (h.target_segment,)
        ).fetchone():
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
                print(f"         → 图谱: {h.source_node} --[{h.edge_type}]--> {h.target_node}")
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
        print("  无确权假设，跳过")
        return

    baseline = con.execute("SELECT AVG(is_lead) FROM user_profile").fetchone()[0] or 0
    edge_lines = []
    for h in confirmed:
        n  = con.execute("SELECT COUNT(*) FROM user_segments WHERE segment=?", (h.target_segment,)).fetchone()[0]
        lr = con.execute("""SELECT AVG(p.is_lead) FROM user_segments s
            JOIN user_profile p ON s.user_id=p.user_id WHERE s.segment=?""",
            (h.target_segment,)).fetchone()[0] or 0
        edge_lines.append(
            f"  {h.source_node} --[{h.edge_type}]--> {h.target_node}"
            f"  (TGI={h.tgi:.0f}, 人群={n:,}人, 留资率={lr:.2%})"
        )

    prompt = f"""你是汽车营销策略专家，目标是触达有购车留资意向的用户。

{_ontology_ctx(G)}

【已确权图谱边（TGI≥{TGI_THRESHOLD}）】
{chr(10).join(edge_lines)}

【全量留资基线】{baseline:.2%}

为每条确权路径生成策略，JSON 数组，每条含：
segment_name, insight, need_path, ad_channel, ad_creative, budget_priority, explainability
只返回 JSON。"""

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
                "ad_creative":    "结合品牌/车型突出金融方案或到店优惠",
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
# 持久化：confirmed_rules.json + ontology.json（增量合并）
# ─────────────────────────────────────────────────────────────────────────────

def _persist(confirmed: list[Hypothesis], G: nx.DiGraph, batch_tag: str) -> None:
    _sep("持久化：confirmed_rules + ontology（增量合并）")

    # 1. confirmed_rules.json：追加本批次确权规则（去重）
    existing_rules: list[dict] = []
    if os.path.exists(CONFIRMED_RULES):
        with open(CONFIRMED_RULES, encoding="utf-8") as f:
            existing_rules = json.load(f)

    existing_keys = {(r["source_node"], r["target_node"], r["edge_type"]) for r in existing_rules}
    new_rules = []
    for h in confirmed:
        key = (h.source_node, h.target_node, h.edge_type)
        if key not in existing_keys:
            d = asdict(h)
            d["batch"] = batch_tag
            new_rules.append(d)
            existing_keys.add(key)
        else:
            # 更新 TGI（取最新值）
            for r in existing_rules:
                if (r["source_node"], r["target_node"], r["edge_type"]) == key:
                    r["tgi"] = h.tgi
                    r["batch_updated"] = batch_tag

    all_rules = existing_rules + new_rules
    with open(CONFIRMED_RULES, "w", encoding="utf-8") as f:
        json.dump(all_rules, f, ensure_ascii=False, indent=2)
    print(f"  confirmed_rules.json: 新增 {len(new_rules)} 条，合计 {len(all_rules)} 条 → {CONFIRMED_RULES}")

    # 2. ontology.json：序列化当前图谱（节点+边），下批次加载时恢复
    nodes_data = {}
    for name, attrs in G.nodes(data=True):
        nodes_data[name] = dict(attrs)

    edges_data = []
    for src, dst, attrs in G.edges(data=True):
        edges_data.append({"src": src, "dst": dst, **attrs})

    with open(ONTOLOGY_FILE, "w", encoding="utf-8") as f:
        json.dump({"nodes": nodes_data, "edges": edges_data}, f, ensure_ascii=False, indent=2)
    print(f"  ontology.json: {G.number_of_nodes()} 节点，{G.number_of_edges()} 边 → {ONTOLOGY_FILE}")


# ─────────────────────────────────────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="规则挖掘（训练集）")
    ap.add_argument("--positive", default=None, help="正样本 JSON 文件")
    ap.add_argument("--negative", default=None, help="负样本 JSON 文件")
    ap.add_argument("--batch",    default=None, help="批次标记（默认=文件名）")
    args = ap.parse_args()

    batch_tag = args.batch or (os.path.basename(args.positive) if args.positive else "manual")

    _sep("双螺旋确权 — 规则挖掘（训练集）")

    con = load(args.positive, args.negative, verbose=True)
    G   = nx.DiGraph()

    run_cep_rules(con)
    run_segment_rules(con)
    init_tbox(G, con)
    hypotheses = generate_hypotheses(G, con)
    confirmed  = validate_hypotheses(hypotheses, con, G)
    generate_strategies(confirmed, G, con)
    _persist(confirmed, G, batch_tag)

    _sep("挖掘完毕")
    print(f"  确权假设: {len(confirmed)} / {len(hypotheses)}")
    print(f"  TBOX 边数: {G.number_of_edges()}")
    _sep()


if __name__ == "__main__":
    main()
