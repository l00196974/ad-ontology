#!/usr/bin/env python3
"""
strategy.py — 策略层
=====================

职责：
  - generate：根据确权假设生成营销策略（LLM 推导 + fallback）
"""

from __future__ import annotations

import sqlite3

import networkx as nx

import config
import llm_client
import ontology
from hypothesis import Hypothesis


def generate(
    confirmed: list[Hypothesis],
    G: nx.DiGraph,
    con: sqlite3.Connection,
) -> list[dict]:
    """
    为每条确权假设生成营销策略。
    优先调用 LLM，失败则使用 fallback 基础策略。
    打印输出并返回策略列表。
    """
    ontology._sep("流程 4：LLM 营销策略生成")
    if not confirmed:
        print("  无确权假设，跳过")
        return []

    baseline = con.execute("SELECT AVG(is_lead) FROM user_profile").fetchone()[0] or 0
    edge_lines = []
    for h in confirmed:
        n  = con.execute(
            "SELECT COUNT(*) FROM user_segments WHERE segment=?", (h.target_segment,)
        ).fetchone()[0]
        lr = con.execute("""
            SELECT AVG(p.is_lead) FROM user_segments s
            JOIN user_profile p ON s.user_id=p.user_id WHERE s.segment=?
        """, (h.target_segment,)).fetchone()[0] or 0
        causal_note = f"  因果注: {h.causal_check[:60]}" if h.causal_check else ""
        edge_lines.append(
            f"  {h.source_node} --[{h.edge_type}]--> {h.target_node}"
            f"  (TGI={h.tgi:.0f}, 人群={n:,}人, 留资率={lr:.2%}){causal_note}"
        )

    prompt = f"""你是汽车营销策略专家，目标是触达有购车留资意向的用户。

{ontology.ontology_ctx(G)}

【已确权图谱边（TGI≥{config.TGI_THRESHOLD}，已通过因果检验）】
{chr(10).join(edge_lines)}

【全量留资基线】{baseline:.2%}

为每条确权路径生成营销策略，JSON 数组，每条含：
segment_name, insight, need_path, ad_channel, ad_creative,
budget_priority（P0/P1/P2+理由）, explainability

只返回 JSON。"""

    print("  [LLM] 策略生成中...", end="", flush=True)
    raw = llm_client.llm_call(prompt)
    strategies: list[dict] = []
    if raw:
        result = llm_client.parse_json_block(raw)
        if isinstance(result, list):
            strategies = result
            print(f"\r  [LLM] 生成 {len(strategies)} 条策略\n")

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
                "segment_name":    h.target_segment,
                "insight":         f"具有 {h.feature_event} 行为，留资率={lr:.2%}",
                "need_path":       f"{h.source_node} → {h.target_node}",
                "ad_channel":      "搜索结果广告",
                "ad_creative":     "结合品牌/车型，突出金融方案或到店优惠",
                "budget_priority": f"P{'0' if h.tgi >= 150 else '1'}",
                "explainability":  f"TGI={h.tgi:.0f}，人群={n:,}人，基线={baseline:.2%}",
            })

    for s in strategies:
        print(f"## {s.get('segment_name','')}")
        print(f"  洞察: {s.get('insight','')}")
        print(f"  链路: {s.get('need_path','')}")
        print(f"  渠道: {s.get('ad_channel','')}")
        print(f"  创意: {s.get('ad_creative','')}")
        print(f"  预算: {s.get('budget_priority','')}")
        print(f"  解释: {s.get('explainability','')}\n")

    return strategies
