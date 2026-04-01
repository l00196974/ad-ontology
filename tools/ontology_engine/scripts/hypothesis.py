#!/usr/bin/env python3
"""
hypothesis.py — 假设层
=======================

职责：
  - Hypothesis dataclass
  - build_prompt：构建多轮假设生成的 LLM prompt
  - generate_multi_round：多轮假设生成 + TGI 验证主流程
"""

from __future__ import annotations

import sqlite3
import sys
from dataclasses import dataclass, field, asdict

import networkx as nx

import config
import analytics
import llm_client
import ontology


# ─────────────────────────────────────────────────────────────────────────────
# Hypothesis 数据类
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
    causal_check: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ─────────────────────────────────────────────────────────────────────────────
# Prompt 构建
# ─────────────────────────────────────────────────────────────────────────────

def build_prompt(
    G: nx.DiGraph,
    con: sqlite3.Connection,
    already_confirmed: list[Hypothesis],
    round_num: int,
    feedback: str = "",
) -> str:
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
        f"  {r[0]}: {r[1]:,}人  留资率={r[2]:.2%}  TGI={r[2]/baseline*100:.0f}"
        for r in seg_rows
    )
    evt_summary = "\n".join(
        f"  {r[0]}: {r[1]:,}用户  留资率={r[2]:.2%}  TGI={r[2]/baseline*100:.0f}"
        for r in evt_rows
    )

    confirmed_str = ""
    if already_confirmed:
        lines = [
            f"  {h.source_node} --[{h.edge_type}]--> {h.target_node} (TGI={h.tgi:.0f})"
            for h in already_confirmed
        ]
        confirmed_str = f"\n【第{round_num-1}轮已确权路径（勿重复）】\n" + "\n".join(lines)

    feedback_str = f"\n【上轮反馈（请据此换视角）】\n{feedback}" if feedback else ""

    return f"""你是汽车营销数据挖掘专家，目标是识别有购车留资意向的用户（留资=提交购车询价）。
这是第 {round_num} 轮推理，请提出新的关系假设路径。

{ontology.ontology_ctx(G)}

【人群分层（含留资率TGI）】
{seg_summary}

【衍生事件（含留资率TGI）】
{evt_summary}

【全量留资基线】{baseline:.2%}
{confirmed_str}
{feedback_str}

【本轮要求】
1. 提出 8 条新的假设，优先探索尚未确权的路径和视角
2. 避免把相关性误认为因果——请在 causal_reasoning 字段说明为什么是因果而非相关
   （例：游泳和冰淇淋销量相关，但原因都是夏天，不是因果）
3. 对于 Triggers_Need（Event→Need）类假设，需说明：
   a) 该事件在时序上是否先于留资（时序检验）
   b) 排除混淆变量的理由（为什么不是第三个变量同时导致了事件和需求）
4. source_node/target_node 必须是图谱中已存在的节点名称
5. edge_type 必须合法
6. 优先选择留资率 TGI≥{config.TGI_THRESHOLD} 的人群-事件组合，数据中已标注 TGI 供参考

返回 JSON 数组，每条含：
  id, description, source_node, target_node, edge_type,
  target_segment, feature_event, causal_reasoning

只返回 JSON。"""


# ─────────────────────────────────────────────────────────────────────────────
# 多轮假设生成 + TGI 验证主流程
# ─────────────────────────────────────────────────────────────────────────────

def generate_multi_round(
    G: nx.DiGraph,
    con: sqlite3.Connection,
    interactive: bool = False,
) -> tuple[list[Hypothesis], list[Hypothesis]]:
    """
    多轮假设生成，返回 (全部假设列表, 确权假设列表)。

    每轮：
      1. 调用 LLM 生成 5 条假设（失败则第1轮用 FALLBACK_HYPOTHESES）
      2. 对每条假设做节点存在性检查 + TGI 计算 + 因果检验
      3. TGI >= TGI_THRESHOLD 则确权并写入图谱
      4. 累计确权数 >= MIN_CONFIRMED 则提前停止
      5. 否则收集 feedback，进入下一轮
    """
    all_hypotheses: list[Hypothesis] = []
    all_confirmed:  list[Hypothesis] = []
    confirmed_edges: set[tuple] = set()  # (source_node, edge_type, target_node) 去重
    feedback = ""

    for rnd in range(1, config.MAX_ROUNDS + 1):
        ontology._sep(f"流程 2+3：第 {rnd} 轮假设生成 + TGI 验证")

        prompt   = build_prompt(G, con, all_confirmed, rnd, feedback)
        print(f"  [LLM] 第{rnd}轮 调用中...", end="", flush=True)
        raw      = llm_client.llm_call(prompt)
        raw_list: list[dict] = []

        if raw:
            result = llm_client.parse_json_block(raw)
            if isinstance(result, list):
                raw_list = result
                print(f"\r  [LLM] 第{rnd}轮 生成 {len(raw_list)} 条假设")

        if not raw_list:
            print(f"\r  [FALLBACK] LLM 无响应，使用内置假设（仅第1轮）")
            if rnd == 1:
                raw_list = config.FALLBACK_HYPOTHESES
            else:
                break

        round_confirmed:    list[Hypothesis] = []
        low_tgi_feedback:   list[str]        = []

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

            # 节点存在性检查
            if hyp.source_node not in G.nodes:
                print(f"  [{hyp.id}] ⚠  source_node 不存在: {hyp.source_node}")
                low_tgi_feedback.append(f"{hyp.id}: source_node={hyp.source_node!r} 不在图谱")
                continue
            if hyp.target_node not in G.nodes:
                print(f"  [{hyp.id}] ⚠  target_node 不存在: {hyp.target_node}")
                low_tgi_feedback.append(f"{hyp.id}: target_node={hyp.target_node!r} 不在图谱")
                continue
            if not con.execute(
                "SELECT 1 FROM user_segments WHERE segment=? LIMIT 1",
                (hyp.target_segment,)
            ).fetchone():
                print(f"  [{hyp.id}] ⚠  segment 不存在: {hyp.target_segment}")
                low_tgi_feedback.append(f"{hyp.id}: segment={hyp.target_segment!r} 不存在")
                continue

            # TGI 计算
            hyp.tgi = round(analytics.compute_tgi(con, hyp.target_segment, hyp.feature_event), 1)
            hyp.confirmed = hyp.tgi >= config.TGI_THRESHOLD
            status = "✅ 确权" if hyp.confirmed else "❌ 未达标"
            print(f"  [{hyp.id}] TGI={hyp.tgi:6.1f}  {status}  {hyp.description}")
            if hyp.causal_check:
                print(f"           因果推理: {hyp.causal_check[:80]}")

            if hyp.confirmed:
                edge_key = (hyp.source_node, hyp.edge_type, hyp.target_node)
                if edge_key in confirmed_edges:
                    print(f"           → 重复路径，跳过")
                    hyp.confirmed = False
                    low_tgi_feedback.append(f"{hyp.id}: 路径 {edge_key} 已确权，请换新路径")
                    continue
                # 因果检验
                warning = analytics.causal_check(con, hyp)
                if warning:
                    print(f"           ⚠ 因果警告: {warning}")
                    hyp.causal_check += f" | 系统警告: {warning}"
                try:
                    ontology.add_edge(
                        G, hyp.source_node, hyp.target_node, hyp.edge_type,
                        tgi=hyp.tgi, hypothesis_id=hyp.id
                    )
                    print(f"           → 写入图谱: {hyp.source_node} --[{hyp.edge_type}]--> {hyp.target_node}")
                    confirmed_edges.add(edge_key)
                    round_confirmed.append(hyp)
                    all_confirmed.append(hyp)
                except ValueError as e:
                    print(f"           ⚠ 合规校验失败: {e}")
            else:
                low_tgi_feedback.append(
                    f"{hyp.id}(TGI={hyp.tgi:.0f}): {hyp.description[:40]} — TGI 低于{config.TGI_THRESHOLD}"
                )

        print(f"\n  第{rnd}轮确权: {len(round_confirmed)} 条，累计确权: {len(all_confirmed)} 条")

        if len(all_confirmed) >= config.MIN_CONFIRMED:
            print(f"  ✅ 已达到最低确权数 {config.MIN_CONFIRMED}，停止迭代")
            break

        if rnd < config.MAX_ROUNDS:
            still_need = config.MIN_CONFIRMED - len(all_confirmed)
            feedback = f"上轮未确权原因（当前已确权 {len(all_confirmed)} 条，还需 {still_need} 条）:\n"
            feedback += "\n".join(f"  - {f}" for f in low_tgi_feedback)
            feedback += "\n\n请换视角，探索其他人群-事件-需求组合，避免重复上轮路径。"

            # 交互确认：是否继续下一轮
            if interactive:
                confirmed_lines = "\n".join(
                    f"  ✅ [{h.id}] TGI={h.tgi:.0f}  {h.description[:60]}"
                    for h in round_confirmed
                ) or "  （本轮无新增确权）"
                detail = (
                    f"  本轮确权 {len(round_confirmed)} 条，累计 {len(all_confirmed)}/{config.MIN_CONFIRMED} 条\n"
                    f"{confirmed_lines}\n"
                    f"  可输入意见引导下一轮（如：'多关注到店意向人群'）"
                )
                print(f"\n{'─'*60}")
                print(f"  ❓ 第 {rnd} 轮已完成，继续第 {rnd+1} 轮推理？")
                print(detail)
                print(f"{'─'*60}")
                print("  [y/Enter] 继续   [n] 停止推理   或直接输入引导意见")
                print("  > ", end="", flush=True)
                try:
                    ans = input().strip()
                except (EOFError, KeyboardInterrupt):
                    print("\n  已中断")
                    break
                if ans.lower() == "n":
                    print("  ⏹  用户停止推理")
                    break
                elif ans.lower() not in ("y", ""):
                    feedback += f"\n\n【用户意见】{ans}"
                    print(f"  📝 已记录意见，将注入下轮 prompt")

            print(f"  🔄 TGI 达标不足（已确权 {len(all_confirmed)}/{config.MIN_CONFIRMED}），进入第 {rnd+1} 轮...")

    print(f"\n  图谱节点数: {G.number_of_nodes()}，总确权边数: {G.number_of_edges()}")
    return all_hypotheses, all_confirmed
