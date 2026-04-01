#!/usr/bin/env python3
"""
亿级智能营销 Agent 与本体推理架构 — 双螺旋确权版 POC v5
=======================================================

工程化入口层，调用各专职模块串联七步流程：
  流程 0A  原始数据加载（data_loader）
  流程 0B  LLM 推导 CEP 规则 → user_derived_events（analytics + llm_client）
  流程 0C  人群规则引擎 → user_segments（analytics）
  流程 1   TBOX 本体初始化（ontology + llm_client）
  流程 2+3 多轮 LLM 假设生成 + ABOX TGI 验证（hypothesis）
  流程 4   LLM 营销策略生成（strategy）

用法：
    python3 scripts/poc_dual_spiral.py
    python3 scripts/poc_dual_spiral.py --positive data/positive.json --negative data/negative.json
    python3 scripts/poc_dual_spiral.py --positive ... --negative ... --reset
    python3 scripts/poc_dual_spiral.py --positive ... --dump-unknown
    python3 scripts/poc_dual_spiral.py --tgi-threshold 130 --max-rounds 5 --min-confirmed 4 ...

    # 分阶段运行（--stop-after 在指定流程后退出）
    python3 scripts/poc_dual_spiral.py --positive ... --negative ... --db cache.db --stop-after load
    python3 scripts/poc_dual_spiral.py --db cache.db --stop-after cep
    python3 scripts/poc_dual_spiral.py --db cache.db --stop-after tbox
    python3 scripts/poc_dual_spiral.py --db cache.db   # 全流程

    # 交互模式（--interactive）
    python3 scripts/poc_dual_spiral.py --db cache.db --interactive

配置覆盖（优先级从高到低）：
    CLI 参数 > 环境变量 > config.py 默认值
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys

import networkx as nx

import config
import analytics
import llm_client
import ontology
import hypothesis as hyp_module
import strategy as strat_module
from data_loader import load as load_data


# ─────────────────────────────────────────────────────────────────────────────
# 交互确认工具
# ─────────────────────────────────────────────────────────────────────────────

def _confirm(title: str, detail: str, interactive: bool) -> tuple[bool, str]:
    """
    交互式确认提示，仿 Claude Code 风格。

    返回 (proceed: bool, extra_feedback: str)
      - proceed=True  → 继续执行
      - proceed=False → 跳过本阶段
      - extra_feedback → 用户输入的额外意见（注入到下一步 prompt）
    """
    if not interactive:
        return True, ""

    print(f"\n{'─'*60}")
    print(f"  ❓ {title}")
    if detail:
        print(detail)
    print(f"{'─'*60}")
    print("  [y] 继续   [n] 跳过   [Enter] 继续   或直接输入修改意见")
    print("  > ", end="", flush=True)

    try:
        ans = input().strip()
    except (EOFError, KeyboardInterrupt):
        print("\n  已中断")
        sys.exit(0)

    if ans.lower() == "n":
        print("  ⏭  已跳过")
        return False, ""
    elif ans.lower() in ("y", ""):
        return True, ""
    else:
        # 用户输入了意见
        print(f"  📝 已记录意见: {ans}")
        return True, ans


# ─────────────────────────────────────────────────────────────────────────────
# 流程 0A：数据加载（含四张表初始化）
# ─────────────────────────────────────────────────────────────────────────────

def _init_full_tables(con: sqlite3.Connection) -> None:
    """初始化全部四张表（含 CEP / Segment 表）"""
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


def build_raw_data(
    con: sqlite3.Connection,
    pos_file: str | None,
    neg_file: str | None,
    dump_unknown: bool = False,
) -> None:
    ontology._sep("流程 0A：原始数据加载")
    _init_full_tables(con)

    if not pos_file and not neg_file:
        from data_loader import _gen_simulated_records, load_records
        print("  [0A-0] 未提供数据文件，生成模拟数据（500正+500负）")
        pos_recs, neg_recs = _gen_simulated_records(500, 500)
        load_records(pos_recs, 1, con)
        load_records(neg_recs, 0, con)
    else:
        from data_loader import read_json_file, load_records
        if pos_file and os.path.exists(pos_file):
            print(f"  [0A-1] 读取正样本: {pos_file}")
            p, e = load_records(read_json_file(pos_file), 1, con)
            print(f"         {p:,} 用户，{e:,} 事件")
        elif pos_file:
            print(f"  [0A-1] ⚠  正样本文件不存在: {pos_file}")
        if neg_file and os.path.exists(neg_file):
            print(f"  [0A-2] 读取负样本: {neg_file}")
            p, e = load_records(read_json_file(neg_file), 0, con)
            print(f"         {p:,} 用户，{e:,} 事件")
        elif neg_file:
            print(f"  [0A-2] ⚠  负样本文件不存在: {neg_file}")

    total_p  = con.execute("SELECT COUNT(*) FROM user_profile").fetchone()[0]
    total_e  = con.execute("SELECT COUNT(*) FROM user_raw_events").fetchone()[0]
    baseline = con.execute("SELECT AVG(is_lead) FROM user_profile").fetchone()[0] or 0
    print(f"\n  全量用户: {total_p:,}，全量事件: {total_e:,}，留资基线: {baseline:.2%}")

    rows = con.execute(
        "SELECT event_type, COUNT(*) n FROM user_raw_events GROUP BY event_type ORDER BY n DESC"
    ).fetchall()
    print("  事件类型分布:")
    for etype, cnt in rows:
        pct = cnt / total_e * 100 if total_e else 0
        print(f"    {etype:<25s} {cnt:>9,} 条  ({pct:.1f}%)")

    if dump_unknown:
        ontology._sep("DUMP：未识别事件 Top 50 样本")
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
# 流程 1：TBOX 初始化
# ─────────────────────────────────────────────────────────────────────────────

def init_tbox(G: nx.DiGraph, con: sqlite3.Connection, interactive: bool = False) -> bool:
    """返回 False 表示用户要求跳过后续流程"""
    ontology._sep("流程 1：TBOX 本体初始化")
    baseline = con.execute("SELECT AVG(is_lead) FROM user_profile").fetchone()[0] or 0

    # User 节点：数据驱动
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
        print(f"  [User ] {seg:<20s} {cnt:>8,} 人  留资率={lr:.2%}  TGI={tgi:.0f}")

    # Event 节点：数据驱动
    evts = con.execute("""
        SELECT derived_event_type, source_rule, COUNT(DISTINCT user_id)
        FROM user_derived_events GROUP BY derived_event_type
    """).fetchall()
    for det, rule, cnt in evts:
        ontology.add_node(G, det, "Event", source_rule=rule, user_count=cnt)
        print(f"  [Event] {det:<28s} {cnt:>8,} 用户")

    # Need/Item/Media：LLM 推导，失败则用 fallback
    nim = llm_client.derive_need_item_media(con, G)
    if nim:
        print("  [LLM] 推导 Need/Item/Media 节点")
        source = "LLM"
    else:
        print("  [FALLBACK] 使用内置 Need/Item/Media 节点")
        nim = config.FALLBACK_NEED_ITEM_MEDIA
        source = "内置"

    for ntype in ["Need", "Item", "Media"]:
        for name in nim.get(ntype, []):
            if name not in G.nodes:
                ontology.add_node(G, name, ntype)
        names = [n for n, d in G.nodes(data=True) if d["node_type"] == ntype]
        print(f"  [{ntype:<5s}][{source}] {', '.join(names)}")

    print(f"\n  合法边类型: {list(config.VALID_EDGES.keys())}")

    # 交互确认：TBOX 结果是否满意
    need_names  = [n for n, d in G.nodes(data=True) if d["node_type"] == "Need"]
    item_names  = [n for n, d in G.nodes(data=True) if d["node_type"] == "Item"]
    media_names = [n for n, d in G.nodes(data=True) if d["node_type"] == "Media"]
    detail = (
        f"  Need : {', '.join(need_names)}\n"
        f"  Item : {', '.join(item_names)}\n"
        f"  Media: {', '.join(media_names)}\n"
        f"  如不满意可输入修改意见（如：'Need 里加一个折扣优惠需求'）"
    )
    proceed, feedback = _confirm("TBOX 节点已生成，是否继续推理？", detail, interactive)
    if not proceed:
        return False

    # 将用户意见写入图谱属性，供假设 prompt 读取
    if feedback:
        G.graph["user_tbox_feedback"] = feedback
    return True


# ─────────────────────────────────────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="双螺旋确权 POC v5 — 留资线索人群挖掘")
    ap.add_argument("--positive",      default=None,  help="正样本 JSON 文件路径")
    ap.add_argument("--negative",      default=None,  help="负样本 JSON 文件路径")
    ap.add_argument("--db",            default=None,  help="SQLite 缓存文件路径（默认 :memory:）；指定后数据持久化，下次跳过导入")
    ap.add_argument("--reset",         action="store_true", help="重新初始化数据库（配合 --db 使用）")
    ap.add_argument("--dump-unknown",  action="store_true", help="打印未识别的 res_key 事件")
    ap.add_argument("--interactive",   action="store_true", help="交互模式：在关键步骤暂停等待用户确认")
    ap.add_argument("--stop-after",    default=None,
                    choices=["load", "cep", "segment", "tbox", "hypothesis"],
                    help="在指定流程后退出（load/cep/segment/tbox/hypothesis）")
    # 配置覆盖（CLI 优先级最高）
    ap.add_argument("--tgi-threshold", type=int,   default=None, help=f"TGI 阈值（默认 {config.TGI_THRESHOLD}）")
    ap.add_argument("--max-rounds",    type=int,   default=None, help=f"最大推理轮数（默认 {config.MAX_ROUNDS}）")
    ap.add_argument("--min-confirmed", type=int,   default=None, help=f"最低确权数（默认 {config.MIN_CONFIRMED}）")
    ap.add_argument("--causal-diff-min",     type=float, default=None, help="因果全局差异阈值")
    ap.add_argument("--causal-ctrl-diff-min",type=float, default=None, help="因果控制差异阈值")
    ap.add_argument("--cep-multi-day-min",   type=int,   default=None, help="CEP多日搜索最小天数")
    ap.add_argument("--cep-brand-search-min",type=int,   default=None, help="CEP品牌搜索最小次数")
    ap.add_argument("--cep-dealer-dur-s",    type=int,   default=None, help="CEP门店停留秒数阈值")
    ap.add_argument("--cep-search-dur-s",    type=int,   default=None, help="CEP搜索停留秒数阈值")
    args = ap.parse_args()

    ia = args.interactive  # 交互模式开关

    # 应用 CLI 覆盖
    config.apply_overrides(
        tgi_threshold=args.tgi_threshold,
        max_rounds=args.max_rounds,
        min_confirmed=args.min_confirmed,
        causal_diff_min=args.causal_diff_min,
        causal_ctrl_diff_min=args.causal_ctrl_diff_min,
        cep_multi_day_min=args.cep_multi_day_min,
        cep_brand_search_min=args.cep_brand_search_min,
        cep_dealer_dur_s=args.cep_dealer_dur_s,
        cep_search_dur_s=args.cep_search_dur_s,
    )

    ontology._sep("双螺旋确权 POC v5 — 留资线索人群挖掘")
    print(f"  配置: TGI≥{config.TGI_THRESHOLD}  最大轮数={config.MAX_ROUNDS}  "
          f"最低确权={config.MIN_CONFIRMED}"
          + ("  [交互模式]" if ia else ""))
    print("  三层流水线: 原始事件(res_key) → LLM推导CEP → 人群分层 → TBOX → 多轮LLM假设 → 策略")

    db_path = args.db or ":memory:"

    # 自动创建父目录
    if db_path != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

    # 判断是否可以复用已有缓存
    use_cache = (
        db_path != ":memory:"
        and os.path.exists(db_path)
        and not args.reset
        and not args.positive
        and not args.negative
    )

    con = sqlite3.connect(db_path)

    if use_cache:
        total_p  = con.execute("SELECT COUNT(*) FROM user_profile").fetchone()[0]
        total_e  = con.execute("SELECT COUNT(*) FROM user_raw_events").fetchone()[0]
        baseline = con.execute("SELECT AVG(is_lead) FROM user_profile").fetchone()[0] or 0
        print(f"\n  [缓存] 复用已有数据库: {db_path}")
        print(f"  全量用户: {total_p:,}，全量事件: {total_e:,}，留资基线: {baseline:.2%}")
        print("  跳过流程 0A（数据导入）")
    else:
        if args.reset and db_path != ":memory:":
            print(f"  [--reset] 清空数据库: {db_path}")
        # 流程 0A
        build_raw_data(con, args.positive, args.negative, dump_unknown=args.dump_unknown)
        if args.dump_unknown:
            return

    if args.stop_after == "load":
        ontology._sep("已在 load 阶段退出（--stop-after load）")
        return

    G = nx.DiGraph()

    # ── 流程 0B：CEP 规则推导 ──────────────────────────────────────────────────
    ontology._sep("流程 0B：CEP 规则引擎（LLM 推导）")
    llm_rules = llm_client.derive_cep_rules(con)
    if llm_rules:
        print(f"  [LLM] 推导出 {len(llm_rules)} 条 CEP 规则")
        cep_rules_to_use = llm_rules
    else:
        builtin = config.get_builtin_cep_rules()
        print(f"  [FALLBACK] LLM 未返回，使用内置 {len(builtin)} 条 CEP 规则")
        cep_rules_to_use = builtin

    # 交互确认：CEP 规则列表
    if ia:
        rule_detail = "\n".join(
            f"  [{i+1}] {r['name']}: {r['desc']}" for i, r in enumerate(cep_rules_to_use)
        )
        proceed, feedback = _confirm(
            f"即将执行 {len(cep_rules_to_use)} 条 CEP 规则，是否继续？",
            rule_detail + "\n  可输入意见修改规则（如：'brand_focused_search 改为至少3次'）",
            ia,
        )
        if not proceed:
            ontology._sep("用户跳过 CEP 执行，程序退出")
            return
        if feedback:
            # 将用户意见追加到 fallback 规则描述，便于后续 LLM 感知
            print(f"  ℹ  用户意见已记录，将在下次 LLM 推导时生效: {feedback}")
            con.execute(
                "CREATE TABLE IF NOT EXISTS _user_feedback(stage TEXT, feedback TEXT)"
            )
            con.execute("INSERT INTO _user_feedback VALUES ('cep', ?)", (feedback,))
            con.commit()

    cep_rules = analytics.run_cep_rules(con, cep_rules_to_use)

    if args.stop_after == "cep":
        ontology._sep("已在 cep 阶段退出（--stop-after cep）")
        return

    # ── 流程 0C：人群规则 ─────────────────────────────────────────────────────
    ontology._sep("流程 0C：人群规则引擎")
    seg_rules = analytics.run_segment_rules(con, cep_rules)

    # 交互确认：人群分层结果
    if ia:
        seg_detail = "\n".join(
            f"  {r['segment']}: {r['rule_desc']}" for r in seg_rules
        )
        proceed, feedback = _confirm(
            "人群分层完成，是否继续初始化 TBOX？",
            seg_detail + "\n  可输入意见调整分层策略",
            ia,
        )
        if not proceed:
            ontology._sep("用户跳过后续流程，程序退出")
            return
        if feedback:
            con.execute(
                "CREATE TABLE IF NOT EXISTS _user_feedback(stage TEXT, feedback TEXT)"
            )
            con.execute("INSERT INTO _user_feedback VALUES ('segment', ?)", (feedback,))
            con.commit()

    if args.stop_after == "segment":
        ontology._sep("已在 segment 阶段退出（--stop-after segment）")
        return

    # ── 流程 1：TBOX ──────────────────────────────────────────────────────────
    if not init_tbox(G, con, interactive=ia):
        ontology._sep("用户跳过假设推理，程序退出")
        return

    if args.stop_after == "tbox":
        ontology._sep("已在 tbox 阶段退出（--stop-after tbox）")
        return

    # ── 流程 2+3：假设生成 ────────────────────────────────────────────────────
    all_hyps, confirmed = hyp_module.generate_multi_round(G, con, interactive=ia)

    if args.stop_after == "hypothesis":
        ontology._sep(f"已在 hypothesis 阶段退出（--stop-after hypothesis）")
        print(f"  总假设数: {len(all_hyps)}，确权: {len(confirmed)}")
        return

    # ── 流程 4：策略生成 ──────────────────────────────────────────────────────
    strat_module.generate(confirmed, G, con)

    ontology._sep("POC 运行完毕")
    print(f"  总假设数: {len(all_hyps)}，确权: {len(confirmed)}")
    print(f"  TBOX 图谱边数: {G.number_of_edges()}")
    ontology._sep()


if __name__ == "__main__":
    main()
