#!/usr/bin/env python3
"""
rule_miner.py — 规则挖掘流程（训练集）
======================================

职责（薄入口，逻辑委托各专职模块）：
  1. 加载训练数据（data_loader）
  2. CEP 规则引擎（analytics）
  3. 人群规则引擎（analytics）
  4. TBOX 本体初始化（ontology + llm_client）
  5. 多轮 LLM 假设生成 + TGI 验证（hypothesis）
  6. LLM 营销策略生成（strategy）
  7. 持久化：confirmed_rules.json + ontology.json（增量合并）

用法：
    python3 scripts/rule_miner.py --positive data/positive.json --negative data/negative.json
    python3 scripts/rule_miner.py --positive data/pos2.json --negative data/neg2.json  # 第二批
    python3 scripts/rule_miner.py --tgi-threshold 130 --max-rounds 5 --positive ...
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3

import networkx as nx

import config
import analytics
import llm_client
import ontology
import hypothesis as hyp_module
import strategy as strat_module
from data_loader import load as load_data
from hypothesis import Hypothesis


# ─────────────────────────────────────────────────────────────────────────────
# TBOX 初始化（含预置节点，不使用 LLM 推导——训练集走确定性流程）
# ─────────────────────────────────────────────────────────────────────────────

def _init_tbox(G: nx.DiGraph, con: sqlite3.Connection) -> None:
    ontology._sep("流程 1：TBOX 本体初始化（增量合并）")
    baseline = con.execute("SELECT AVG(is_lead) FROM user_profile").fetchone()[0] or 0

    # 先恢复已有本体（跨批次持久化）
    ontology.restore_graph(G)

    # 本批次 User 节点
    segs = con.execute(
        "SELECT segment, segment_rule, COUNT(*) FROM user_segments GROUP BY segment"
    ).fetchall()
    for seg, rule, cnt in segs:
        lr = con.execute("""
            SELECT AVG(p.is_lead) FROM user_segments s
            JOIN user_profile p ON s.user_id=p.user_id WHERE s.segment=?
        """, (seg,)).fetchone()[0] or 0
        tgi = lr / baseline * 100 if baseline > 0 else 0
        ontology.add_node(G, seg, "User",
                          segment_rule=rule, user_count=cnt,
                          lead_rate=round(lr, 4), tgi=round(tgi, 1))
        print(f"  [User ] {seg:<16s} {cnt:>6,} 人  留资率={lr:.2%}  TGI={tgi:.0f}")

    # 本批次 Event 节点
    evts = con.execute("""
        SELECT derived_event_type, source_rule, COUNT(DISTINCT user_id)
        FROM user_derived_events GROUP BY derived_event_type
    """).fetchall()
    for det, rule, cnt in evts:
        ontology.add_node(G, det, "Event", source_rule=rule, user_count=cnt)
        print(f"  [Event] {det:<28s} {cnt:>6,} 用户")

    # 预置 Need/Item/Media 节点（fallback，训练集不依赖 LLM）
    for name, ntype in [(n, t) for t, nodes in config.FALLBACK_NEED_ITEM_MEDIA.items()
                        for n in nodes]:
        if name not in G.nodes:
            ontology.add_node(G, name, ntype)

    for ntype in ["Need", "Item", "Media"]:
        names = [n for n, d in G.nodes(data=True) if d["node_type"] == ntype]
        print(f"  [{ntype:<5s}] {', '.join(names)}")


# ─────────────────────────────────────────────────────────────────────────────
# 持久化：confirmed_rules.json + ontology.json（增量合并）
# ─────────────────────────────────────────────────────────────────────────────

def _persist(confirmed: list[Hypothesis], G: nx.DiGraph, batch_tag: str) -> None:
    ontology._sep("持久化：confirmed_rules + ontology（增量合并）")

    # confirmed_rules.json：追加本批次确权规则（相同路径更新 TGI）
    existing_rules: list[dict] = []
    if os.path.exists(config.CONFIRMED_RULES_PATH):
        with open(config.CONFIRMED_RULES_PATH, encoding="utf-8") as f:
            existing_rules = json.load(f)

    existing_keys = {
        (r["source_node"], r["target_node"], r["edge_type"]) for r in existing_rules
    }
    new_rules = []
    for h in confirmed:
        key = (h.source_node, h.target_node, h.edge_type)
        if key not in existing_keys:
            d = h.to_dict()
            d["batch"] = batch_tag
            new_rules.append(d)
            existing_keys.add(key)
        else:
            for r in existing_rules:
                if (r["source_node"], r["target_node"], r["edge_type"]) == key:
                    r["tgi"] = h.tgi
                    r["batch_updated"] = batch_tag

    all_rules = existing_rules + new_rules
    with open(config.CONFIRMED_RULES_PATH, "w", encoding="utf-8") as f:
        json.dump(all_rules, f, ensure_ascii=False, indent=2)
    print(f"  confirmed_rules.json: 新增 {len(new_rules)} 条，合计 {len(all_rules)} 条 → {config.CONFIRMED_RULES_PATH}")

    # ontology.json：序列化当前图谱
    ontology.save_ontology(G)
    print(f"  ontology.json: {G.number_of_nodes()} 节点，{G.number_of_edges()} 边 → {config.ONTOLOGY_PATH}")


# ─────────────────────────────────────────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────────────────────────────────────────

def mine(pos_file: str | None, neg_file: str | None, batch_tag: str) -> None:
    ontology._sep("双螺旋确权 — 规则挖掘（训练集）")
    print(f"  配置: TGI≥{config.TGI_THRESHOLD}  最大轮数={config.MAX_ROUNDS}  "
          f"最低确权={config.MIN_CONFIRMED}")

    con = load_data(pos_file, neg_file, verbose=True)

    # 补充 CEP/Segment 表（data_loader 只建了 user_profile + user_raw_events）
    con.executescript("""
        CREATE TABLE IF NOT EXISTS user_derived_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT, event_time TEXT,
            derived_event_type TEXT, source_rule TEXT, attr_json TEXT
        );
        CREATE TABLE IF NOT EXISTS user_segments (
            user_id TEXT, segment TEXT, segment_rule TEXT, derived_at TEXT
        );
    """)

    G = nx.DiGraph()

    ontology._sep("流程 0B：CEP 规则引擎")
    cep_rules = analytics.run_cep_rules(con, config.get_builtin_cep_rules())

    ontology._sep("流程 0C：人群规则引擎")
    analytics.run_segment_rules(con, cep_rules)

    _init_tbox(G, con)

    all_hyps, confirmed = hyp_module.generate_multi_round(G, con)
    strat_module.generate(confirmed, G, con)
    _persist(confirmed, G, batch_tag)

    ontology._sep("挖掘完毕")
    print(f"  确权假设: {len(confirmed)} / {len(all_hyps)}")
    print(f"  TBOX 边数: {G.number_of_edges()}")
    ontology._sep()


# ─────────────────────────────────────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="规则挖掘（训练集）")
    ap.add_argument("--positive", default=None, help="正样本 JSON 文件")
    ap.add_argument("--negative", default=None, help="负样本 JSON 文件")
    ap.add_argument("--batch",    default=None, help="批次标记（默认=文件名）")
    ap.add_argument("--tgi-threshold", type=int,   default=None)
    ap.add_argument("--max-rounds",    type=int,   default=None)
    ap.add_argument("--min-confirmed", type=int,   default=None)
    args = ap.parse_args()

    config.apply_overrides(
        tgi_threshold=args.tgi_threshold,
        max_rounds=args.max_rounds,
        min_confirmed=args.min_confirmed,
    )

    batch_tag = args.batch or (os.path.basename(args.positive) if args.positive else "manual")
    mine(args.positive, args.negative, batch_tag)


if __name__ == "__main__":
    main()
