#!/usr/bin/env python3
"""
strategy.py — 策略层
=====================

职责：
  - generate：根据确权假设生成营销策略（LLM 推导 + fallback）
  - audience_chains：从 Item 出发反向遍历 Need→Event→User，打印完整投放链路
"""

from __future__ import annotations

import sqlite3

import networkx as nx

import config
import llm_client
import ontology
from hypothesis import Hypothesis


def audience_chains(confirmed: list[Hypothesis], G: nx.DiGraph, con: sqlite3.Connection) -> list[dict]:  # noqa: C901
    """
    反向查找链：Item → Need → Event → User Segment

    对每个 Item 节点，找所有 Satisfied_By 关联的 Need，
    再找 Need 上所有 Triggers_Need 关联的 Event（按 weight 降序），
    再从 user_derived_events 查出满足该 Event 的用户集合和 TGI。

    如果 user_need_scores 表存在，额外展示每个 Need 的主导用户数。

    返回结构化的投放链路列表，供策略 prompt 使用。
    """
    baseline = con.execute("SELECT AVG(is_lead) FROM user_profile").fetchone()[0] or 0
    chains = []

    # 检查 Need 打分表是否存在
    has_need_scores = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='user_need_scores'"
    ).fetchone() is not None

    items = [n for n, d in G.nodes(data=True) if d.get("node_type") == "Item"]
    for item in items:
        # Item ← Satisfied_By ← Need
        needs_for_item = [
            src for src, dst, d in G.in_edges(item, data=True)
            if d.get("edge_type") == "Satisfied_By"
        ]
        if not needs_for_item:
            continue

        item_chain: dict = {"item": item, "needs": []}
        for need in needs_for_item:
            # Need ← Triggers_Need ← Event
            events_for_need = sorted(
                [
                    (src, d.get("weight", 1.0), d.get("tgi", 0))
                    for src, dst, d in G.in_edges(need, data=True)
                    if d.get("edge_type") == "Triggers_Need"
                ],
                key=lambda x: x[1], reverse=True  # weight 降序
            )
            if not events_for_need:
                continue

            # Need 主导用户数（来自 user_need_scores）
            dominant_user_count = 0
            if has_need_scores:
                dominant_user_count = con.execute(
                    "SELECT COUNT(*) FROM user_need_scores WHERE need_name=? AND dominant_flag=1",
                    (need,)
                ).fetchone()[0]

            need_entry: dict = {
                "need": need,
                "dominant_user_count": dominant_user_count,
                "events": [],
            }
            for event_name, weight, edge_tgi in events_for_need:
                # Event → User（从 user_derived_events 查实际人群）
                n = con.execute(
                    "SELECT COUNT(DISTINCT user_id) FROM user_derived_events WHERE derived_event_type=?",
                    (event_name,)
                ).fetchone()[0]
                lr = con.execute("""
                    SELECT AVG(p.is_lead) FROM user_derived_events d
                    JOIN user_profile p ON d.user_id=p.user_id
                    WHERE d.derived_event_type=?
                """, (event_name,)).fetchone()[0] or 0
                tgi = lr / baseline * 100 if baseline > 0 else edge_tgi
                need_entry["events"].append({
                    "event": event_name,
                    "weight": weight,
                    "user_count": n,
                    "lead_rate": round(lr, 4),
                    "tgi": round(tgi, 1),
                })
            item_chain["needs"].append(need_entry)
        if item_chain["needs"]:
            chains.append(item_chain)

    # 打印反向链路
    if chains:
        ontology._sep("投放链路：Item → Need → Event → User")
        for item_chain in chains:
            print(f"\n  📦 {item_chain['item']}")
            for need_entry in item_chain["needs"]:
                dom_str = f"  [主导用户={need_entry['dominant_user_count']:,}]" if need_entry.get("dominant_user_count") else ""
                print(f"    └─ Need: {need_entry['need']}{dom_str}")
                for ev in need_entry["events"]:
                    print(f"         └─ Event: {ev['event']:<30s}  "
                          f"weight={ev['weight']:.2f}  "
                          f"用户={ev['user_count']:>8,}  "
                          f"TGI={ev['tgi']:.0f}")

    # 打印人工 Need 圈选人群（来自 user_need_segments，独立于 Event 关系）
    has_need_segs = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='user_need_segments'"
    ).fetchone() is not None
    if has_need_segs:
        baseline = con.execute("SELECT AVG(is_lead) FROM user_profile").fetchone()[0] or 0
        seg_rows = con.execute("""
            SELECT n.need_name, COUNT(*) n_users, MAX(n.rule_expr) rule_expr, MAX(n.description) description
            FROM user_need_segments n
            GROUP BY n.need_name
        """).fetchall()
        if seg_rows:
            # 从 user_need_scores 取 TGI（若表存在）
            tgi_from_scores: dict[str, float] = {}
            if has_need_scores:
                rows_t = con.execute(
                    "SELECT need_name, AVG(tgi) FROM user_need_scores GROUP BY need_name"
                ).fetchall()
                tgi_from_scores = {r[0]: r[1] for r in rows_t}

            ontology._sep("人工 Need 圈选人群（基于规则表达式）")
            for need_name, n_users, rule, desc in seg_rows:
                lr = con.execute("""
                    SELECT AVG(p.is_lead) FROM user_need_segments ns
                    JOIN user_profile p ON ns.user_id=p.user_id WHERE ns.need_name=?
                """, (need_name,)).fetchone()[0] or 0
                tgi = tgi_from_scores.get(need_name) or (lr / baseline * 100 if baseline > 0 else 0)
                tag = "🥩肉" if tgi >= 120 else ("🧂盐" if tgi >= 60 else "☠️毒药(排雷)")
                desc_str = f"  {desc}" if desc else ""
                print(f"  {tag}  {need_name:<25s}  用户={n_users:>8,}  留资率={lr:.2%}  TGI={tgi:.0f}{desc_str}")
                if rule:
                    print(f"       规则: {rule[:80]}")

    return chains


def generate(
    confirmed: list[Hypothesis],
    G: nx.DiGraph,
    con: sqlite3.Connection,
) -> list[dict]:
    """
    为每条确权假设生成营销策略。
    先打印 Item→Need→Event→User 反向链路，再调用 LLM 生成策略。
    """
    ontology._sep("流程 4：LLM 营销策略生成")
    if not confirmed:
        print("  无确权假设，跳过")
        return []

    # 构建并打印反向链路
    chains = audience_chains(confirmed, G, con)

    baseline = con.execute("SELECT AVG(is_lead) FROM user_profile").fetchone()[0] or 0

    # 构建 LLM prompt 的边摘要
    edge_lines = []
    for h in confirmed:
        n  = con.execute(
            "SELECT COUNT(*) FROM user_segments WHERE segment=?", (h.target_segment,)
        ).fetchone()[0]
        lr = con.execute("""
            SELECT AVG(p.is_lead) FROM user_segments s
            JOIN user_profile p ON s.user_id=p.user_id WHERE s.segment=?
        """, (h.target_segment,)).fetchone()[0] or 0
        weight_str = f"  weight={h.weight:.2f}" if h.edge_type == "Triggers_Need" else ""
        causal_note = f"  因果注: {h.causal_check[:50]}" if h.causal_check else ""
        edge_lines.append(
            f"  {h.source_node} --[{h.edge_type}]--> {h.target_node}"
            f"  (TGI={h.tgi:.0f}, 人群={n:,}人, 留资率={lr:.2%}){weight_str}{causal_note}"
        )

    # 构建链路摘要给 LLM
    chain_summary = ""
    if chains:
        lines = []
        for c in chains:
            for ne in c["needs"]:
                dom_str = f", 主导用户={ne['dominant_user_count']:,}" if ne.get("dominant_user_count") else ""
                for ev in ne["events"]:
                    lines.append(
                        f"  {c['item']} ← {ne['need']} ← {ev['event']}"
                        f"  (weight={ev['weight']:.2f}, 用户={ev['user_count']:,}, TGI={ev['tgi']:.0f}{dom_str})"
                    )
        chain_summary = "\n【反向链路（Item←Need←Event←User）】\n" + "\n".join(lines)

    # 构建排雷人群摘要（TGI<60，exclusion_flag=1）
    exclusion_summary = ""
    has_scores = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='user_need_scores'"
    ).fetchone() is not None
    if has_scores:
        excl_rows = con.execute("""
            SELECT need_name, COUNT(*) n, AVG(tgi) tgi
            FROM user_need_scores
            WHERE exclusion_flag=1
            GROUP BY need_name
            ORDER BY tgi ASC
        """).fetchall()
        if excl_rows:
            excl_lines = [
                f"  {r[0]}（用户={r[1]:,}，TGI={r[2]:.0f}）" for r in excl_rows
            ]
            exclusion_summary = "\n【排雷人群（TGI<60，投放时应作为排除定向）】\n" + "\n".join(excl_lines)

    prompt = f"""你是汽车营销策略专家，目标是触达有购车留资意向的用户。

{ontology.ontology_ctx(G)}

【已确权图谱边（TGI≥{config.TGI_THRESHOLD}，已通过因果检验）】
{chr(10).join(edge_lines)}
{chain_summary}
{exclusion_summary}

【全量留资基线】{baseline:.2%}

【策略生成要求】
1. 基于 Item←Need←Event←User 的反向链路，为每个高优先级 Item 生成投放策略
2. 同一个 Need 可能对应多个触发 Event，策略中需说明主要触发路径
3. weight 越高的 Event 触发对应 Need 的强度越大，优先选择高 weight 路径
4. "主导用户"指经 Need 分值 Softmax 后以该 Need 为第一意图的用户，是最高价值投放人群
5. 人群圈选方式：通过 Event 的 CEP 规则圈定用户，不能用留资本身作为圈选条件
6. 排雷人群（TGI<60）需在投放定向中明确排除，避免广告预算浪费

为每条高价值链路生成投放策略，JSON 数组，每条含：
  item_name, need_triggered, key_events（主要触发事件列表）,
  audience_size（估算触达人数）, dominant_audience（主导意图用户数）,
  exclusion_audiences（排雷人群列表，需排除的 Need 人群名称）,
  segment_insight, ad_channel, ad_creative,
  budget_priority（P0/P1/P2+理由）, explainability

只返回 JSON。"""

    print("\n  [LLM] 策略生成中：")
    raw = llm_client.llm_call(prompt)
    strategies: list[dict] = []
    if raw:
        result = llm_client.parse_json_block(raw)
        if isinstance(result, list):
            strategies = result
            print(f"  [LLM] 解析出 {len(strategies)} 条策略\n")

    if not strategies:
        print("  [FALLBACK] 基础策略\n")
        for h in confirmed:
            n  = con.execute(
                "SELECT COUNT(*) FROM user_segments WHERE segment=?", (h.target_segment,)
            ).fetchone()[0]
            lr = con.execute("""
                SELECT AVG(p.is_lead) FROM user_segments s
                JOIN user_profile p ON s.user_id=p.user_id WHERE s.segment=?
            """, (h.target_segment,)).fetchone()[0] or 0
            strategies.append({
                "item_name":       h.target_node if G.nodes[h.target_node]["node_type"] == "Item" else "",
                "need_triggered":  h.target_node if G.nodes[h.target_node]["node_type"] == "Need" else "",
                "key_events":      [h.feature_event],
                "audience_size":   n,
                "segment_insight": f"具有 {h.feature_event} 行为，留资率={lr:.2%}，TGI={h.tgi:.0f}",
                "ad_channel":      "搜索结果广告",
                "ad_creative":     "结合品牌/车型，突出金融方案或到店优惠",
                "budget_priority": f"P{'0' if h.tgi >= 150 else '1'}",
                "explainability":  f"TGI={h.tgi:.0f}，人群={n:,}人，基线={baseline:.2%}",
            })

    for s in strategies:
        item = s.get("item_name") or s.get("need_triggered") or s.get("segment_name", "")
        print(f"## {item}")
        if s.get("need_triggered"):
            print(f"  需求: {s.get('need_triggered','')}")
        if s.get("key_events"):
            print(f"  触发事件: {', '.join(s.get('key_events', []))}")
        if s.get("audience_size"):
            print(f"  预估人群: {s.get('audience_size'):,} 人" if isinstance(s.get("audience_size"), int) else f"  预估人群: {s.get('audience_size')}")
        if s.get("dominant_audience"):
            print(f"  主导意图用户: {s.get('dominant_audience'):,} 人" if isinstance(s.get("dominant_audience"), int) else f"  主导意图用户: {s.get('dominant_audience')}")
        print(f"  洞察: {s.get('segment_insight', s.get('insight',''))}")
        print(f"  渠道: {s.get('ad_channel','')}")
        print(f"  创意: {s.get('ad_creative','')}")
        print(f"  预算: {s.get('budget_priority','')}")
        print(f"  解释: {s.get('explainability','')}\n")

    return strategies

