#!/usr/bin/env python3
"""
analytics.py — 分析层
======================

职责：
  - TGI 计算：compute_tgi / seg_stats
  - CEP 规则引擎：run_cep_rules（执行规则列表，写入 user_derived_events）
  - 人群规则引擎：run_segment_rules（写入 user_segments）
  - 因果检验：causal_check（有/无事件留资率对比 + 控制变量检验）
  - Need 打分（图谱路径）：compute_need_scores（W_base × 时间衰减 × 竞争力 → Softmax）
  - Need 打分（规则路径）：compute_need_scores_from_rules（满足度 × 时间衰减 × IDF → Softmax）
"""

from __future__ import annotations

import json
import math
import sqlite3
import sys
from datetime import datetime
from typing import TYPE_CHECKING

import networkx as nx

import config
import bitmap_engine as bm_eng

if TYPE_CHECKING:
    from hypothesis import Hypothesis


# ─────────────────────────────────────────────────────────────────────────────
# TGI 计算
# ─────────────────────────────────────────────────────────────────────────────

def compute_tgi(
    con: sqlite3.Connection,
    target_segment: str,
    feature_event: str,
) -> float:
    """
    TGI = (segment内有feature_event用户的留资率 / 全量留资率) × 100
    """
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


def seg_stats(con: sqlite3.Connection, segment: str) -> tuple[int, float]:
    """返回 (人数, 留资率)"""
    n = con.execute(
        "SELECT COUNT(*) FROM user_segments WHERE segment=?", (segment,)
    ).fetchone()[0]
    lr = con.execute("""
        SELECT AVG(p.is_lead) FROM user_segments s
        JOIN user_profile p ON s.user_id=p.user_id WHERE s.segment=?
    """, (segment,)).fetchone()[0] or 0
    return n, lr


# ─────────────────────────────────────────────────────────────────────────────
# CEP 规则引擎
# ─────────────────────────────────────────────────────────────────────────────

def run_cep_rules(
    con: sqlite3.Connection,
    rules: list[dict],
    append: bool = False,
) -> list[dict]:
    """
    执行 CEP 规则列表，写入 user_derived_events，打印统计并返回成功规则。

    规则可以有两种字段：
      - "sql"       旧路径：直接执行 INSERT SELECT SQL（config.py 内置规则用此路径）
      - "rule_expr" 新路径：解析 raw.* 表达式，用 BitmapContext 批量执行（共享缓存）

    append=False（默认）：先清空 user_derived_events 再执行（初始运行）
    append=True：不清空，直接追加新规则结果（多轮补充）
    """
    if not append:
        print("  清空旧衍生事件...", end="", flush=True)
        con.execute("DELETE FROM user_derived_events")
        con.commit()
        print("\r  旧衍生事件已清空")

    baseline = con.execute("SELECT AVG(is_lead) FROM user_profile").fetchone()[0] or 0
    used_rules: list[dict] = []

    # 分拣：有 rule_expr 字段的走 bitmap，其余走 sql
    sql_rules  = [r for r in rules if r.get("sql") and not r.get("rule_expr")]
    expr_rules = [r for r in rules if r.get("rule_expr")]

    # ── 旧路径：直接执行 SQL ───────────────────────────────────────────────
    for rule in sql_rules:
        name = rule.get("name", "")
        desc = rule.get("desc", "")
        sql  = rule.get("sql", "")
        try:
            print(f"  {name:<28s} → 执行中...", end="", flush=True)
            con.execute(sql)
            con.commit()
            n = con.execute(
                "SELECT COUNT(DISTINCT user_id) FROM user_derived_events WHERE derived_event_type=?",
                (name,)
            ).fetchone()[0]
            if n == 0:
                print(f"\r  {name:<28s} → 0 用户，跳过")
                continue
            lr  = con.execute("""
                SELECT AVG(p.is_lead) FROM user_derived_events d
                JOIN user_profile p ON d.user_id=p.user_id WHERE d.derived_event_type=?
            """, (name,)).fetchone()[0] or 0
            tgi = lr / baseline * 100 if baseline > 0 else 0
            print(f"\r  {name:<28s} {n:>8,} 用户  留资率={lr:.2%}  TGI={tgi:.0f}  {desc}")
            used_rules.append(rule)
        except Exception as e:
            print(f"\r  {name:<28s} SQL执行失败: {e}")

    # ── 新路径：rule_expr 表达式 → BitmapContext 批量执行 ─────────────────
    if expr_rules:
        now_str = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        ctx = bm_eng.BitmapContext(con)
        print(f"  [Bitmap] 初始化完成：{ctx.registry.size:,} 名用户，处理 {len(expr_rules)} 条 rule_expr 规则")
        for rule in expr_rules:
            name = rule.get("name", "")
            desc = rule.get("desc", "")
            expr = rule.get("rule_expr", "")
            try:
                print(f"  {name:<28s} → Bitmap 圈选中...", end="", flush=True)
                bm   = ctx.eval_expr(expr)
                n    = ctx.popcount(bm)
                if n == 0:
                    print(f"\r  {name:<28s} → 0 用户，跳过")
                    continue
                uids = ctx.to_user_ids(bm)
                con.executemany(
                    "INSERT OR IGNORE INTO user_derived_events"
                    "(user_id,event_time,derived_event_type,source_rule,attr_json) VALUES(?,?,?,?,?)",
                    [(uid, now_str, name, expr, "{}") for uid in uids],
                )
                con.commit()
                lr  = con.execute("""
                    SELECT AVG(p.is_lead) FROM user_derived_events d
                    JOIN user_profile p ON d.user_id=p.user_id WHERE d.derived_event_type=?
                """, (name,)).fetchone()[0] or 0
                tgi = lr / baseline * 100 if baseline > 0 else 0
                print(f"\r  {name:<28s} {n:>8,} 用户  留资率={lr:.2%}  TGI={tgi:.0f}  {desc}")
                used_rules.append(rule)
            except Exception as e:
                print(f"\r  {name:<28s} 执行失败: {e}")
        stats = ctx.cache_stats()
        print(f"  [Bitmap] 缓存命中={stats['hits']} 未命中={stats['misses']} 条目={stats['cached']}")

    return used_rules


# ─────────────────────────────────────────────────────────────────────────────
# 人群规则引擎
# ─────────────────────────────────────────────────────────────────────────────

def run_segment_rules(con: sqlite3.Connection, cep_rules: list[dict]) -> list[dict]:
    """
    根据 CEP 规则自动生成 segment，写入 user_segments，打印统计并返回 seg_rules。

    每条 CEP 规则对应一个 segment：
      - rule 中若有 "segment_name" 字段则用之，否则用 rule["name"] 作为 segment 名
    """
    print("  清空旧人群标签...", end="", flush=True)
    con.execute("DELETE FROM user_segments")
    con.commit()
    print("\r  旧人群标签已清空")

    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    baseline = con.execute("SELECT AVG(is_lead) FROM user_profile").fetchone()[0] or 0
    seg_rules: list[dict] = []

    for rule in cep_rules:
        name = rule.get("name", "")
        seg  = rule.get("segment_name") or name
        desc = rule.get("desc", name)
        print(f"  {seg:<20s}  → 写入中...", end="", flush=True)
        con.execute(
            "INSERT INTO user_segments(user_id,segment,segment_rule,derived_at)"
            " SELECT DISTINCT user_id,?,?,? FROM user_derived_events WHERE derived_event_type=?",
            (seg, desc, now, name)
        )
        con.commit()
        n = con.execute("SELECT COUNT(*) FROM user_segments WHERE segment=?", (seg,)).fetchone()[0]
        lr = con.execute("""
            SELECT AVG(p.is_lead) FROM user_segments s
            JOIN user_profile p ON s.user_id=p.user_id WHERE s.segment=?
        """, (seg,)).fetchone()[0] or 0
        tgi = lr / baseline * 100 if baseline > 0 else 0
        print(f"\r  {seg:<20s}  {n:>8,} 人  留资率={lr:.2%}  TGI={tgi:.0f}")
        seg_rules.append({"segment": seg, "feature_event": name, "rule_desc": desc})

    return seg_rules


# ─────────────────────────────────────────────────────────────────────────────
# 因果检验
# ─────────────────────────────────────────────────────────────────────────────

def causal_check(con: sqlite3.Connection, h: "Hypothesis") -> str:
    """
    对 Triggers_Need（Event→Need）类假设做简单因果检验：
      1. 全局检验：有/无该衍生事件的用户留资率差异是否 >= CAUSAL_DIFF_MIN
      2. 控制变量检验：在同一 segment 内，有/无该事件的留资率差异是否 >= CAUSAL_CTRL_DIFF_MIN

    返回警告字符串（空字符串 = 无警告）
    """
    if h.edge_type != "Triggers_Need":
        return ""

    feat = h.feature_event
    seg  = h.target_segment

    # 全局检验
    lr_with = con.execute("""
        SELECT AVG(p.is_lead) FROM user_profile p
        WHERE EXISTS (
            SELECT 1 FROM user_derived_events d
            WHERE d.user_id=p.user_id AND d.derived_event_type=?
        )
    """, (feat,)).fetchone()[0] or 0

    lr_without = con.execute("""
        SELECT AVG(p.is_lead) FROM user_profile p
        WHERE NOT EXISTS (
            SELECT 1 FROM user_derived_events d
            WHERE d.user_id=p.user_id AND d.derived_event_type=?
        )
    """, (feat,)).fetchone()[0] or 0

    diff = lr_with - lr_without
    if diff < config.CAUSAL_DIFF_MIN:
        return (
            f"有{feat}事件留资率={lr_with:.2%} vs 无={lr_without:.2%}，"
            f"差异仅{diff:.2%}，因果效应弱，注意排除混淆变量"
        )

    # 控制变量检验：在 segment 内对比
    lr_seg_with = con.execute("""
        SELECT AVG(p.is_lead) FROM user_segments s
        JOIN user_profile p ON s.user_id=p.user_id
        WHERE s.segment=?
          AND EXISTS (
              SELECT 1 FROM user_derived_events d
              WHERE d.user_id=s.user_id AND d.derived_event_type=?
          )
    """, (seg, feat)).fetchone()[0] or 0

    lr_seg_without = con.execute("""
        SELECT AVG(p.is_lead) FROM user_segments s
        JOIN user_profile p ON s.user_id=p.user_id
        WHERE s.segment=?
          AND NOT EXISTS (
              SELECT 1 FROM user_derived_events d
              WHERE d.user_id=s.user_id AND d.derived_event_type=?
          )
    """, (seg, feat)).fetchone()[0] or 0

    seg_diff = lr_seg_with - lr_seg_without
    if seg_diff < config.CAUSAL_CTRL_DIFF_MIN and lr_seg_without > 0:
        return (
            f"在{seg}内，有/无{feat}的留资率差仅{seg_diff:.2%}，"
            f"控制人群变量后效应消失，该关系可能为相关性非因果"
        )

    return ""


# ─────────────────────────────────────────────────────────────────────────────
# Need 打分系统（Weight Fusion Mechanism）
# ─────────────────────────────────────────────────────────────────────────────

def compute_need_scores(
    con: sqlite3.Connection,
    G: nx.DiGraph,
    brand: str | None = None,
    time_decay_halflife_days: float = 7.0,
) -> list[dict]:
    """
    为每个用户计算 Need 分值向量，写入 user_need_scores 表。

    完整公式（四层相乘）：
      贡献 = W_base(need) × edge_weight × time_decay × C(brand, need)

    其中：
    1. 离线层（W_base）：IDF 思路，TGI 越高、覆盖越窄的 Need 权重越大
       W_base(need) = mean_TGI × log(N / (user_count + 1))，归一化到 [0,1]

    2. 近线层（S_moment）：时间衰减动量
       time_decay = e^{-λt}，λ = ln(2) / halflife_days

    3. 竞争力层（C）：广告主品牌在该 Need 维度的竞争力系数
       从 brand_need_competitiveness 表读取，默认 1.0
       brand=None 时全部取 1.0（无品牌视角）

    4. 在线层（Softmax）：
       normalized_score ∈ (0,1)，dominant_flag=1 标记最高分 Need

    参数：
      brand: 广告主品牌名（需与 brand_need_competitiveness.brand 一致），None 表示不区分品牌
    """
    from ontology import _sep
    _sep(f"Need 打分系统（品牌={brand or '不区分'} · W_base × 时间衰减 × 竞争力 → Softmax）")

    # ── 建表 ─────────────────────────────────────────────────────────────────
    con.executescript("""
        DROP TABLE IF EXISTS user_need_scores;
        CREATE TABLE user_need_scores (
            user_id          TEXT,
            need_name        TEXT,
            raw_score        REAL,
            normalized_score REAL,
            dominant_flag    INTEGER DEFAULT 0,
            computed_at      TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_uns_user ON user_need_scores(user_id);
        CREATE INDEX IF NOT EXISTS idx_uns_need  ON user_need_scores(need_name);
    """)

    # ── 确保竞争力配置表存在（不重建，保留用户已导入的数据）────────────────
    con.execute("""
        CREATE TABLE IF NOT EXISTS brand_need_competitiveness (
            brand      TEXT NOT NULL,
            need_name  TEXT NOT NULL,
            score      REAL NOT NULL DEFAULT 1.0,
            updated_at TEXT,
            PRIMARY KEY (brand, need_name)
        )
    """)
    con.commit()

    # ── 收集图中所有 Triggers_Need 边 ──────────────────────────────────────
    triggers_edges: list[tuple[str, str, float, float]] = []  # (event, need, weight, tgi)
    for src, dst, d in G.edges(data=True):
        if d.get("edge_type") == "Triggers_Need":
            triggers_edges.append((src, dst, float(d.get("weight", 1.0)), float(d.get("tgi", 100.0))))

    if not triggers_edges:
        print("  ⚠  图中无 Triggers_Need 边，跳过 Need 打分")
        return []

    print(f"  Triggers_Need 边数: {len(triggers_edges)}")

    # ── 离线层：计算 W_base ──────────────────────────────────────────────────
    N_total = con.execute("SELECT COUNT(*) FROM user_profile").fetchone()[0] or 1

    # 按 Need 聚合：均值 TGI、覆盖用户数（所有触发该 Need 的 Event 的用户并集）
    need_tgi_sum: dict[str, list[float]] = {}
    need_events:  dict[str, list[str]]   = {}
    for event_name, need_name, edge_weight, edge_tgi in triggers_edges:
        need_tgi_sum.setdefault(need_name, []).append(edge_tgi)
        need_events.setdefault(need_name, []).append(event_name)

    w_base: dict[str, float] = {}
    for need_name, tgi_list in need_tgi_sum.items():
        mean_tgi = sum(tgi_list) / len(tgi_list)
        events = need_events[need_name]
        placeholders = ",".join("?" * len(events))
        user_count = con.execute(
            f"SELECT COUNT(DISTINCT user_id) FROM user_derived_events WHERE derived_event_type IN ({placeholders})",
            events,
        ).fetchone()[0] or 0
        idf = math.log(N_total / (user_count + 1))
        w_base[need_name] = mean_tgi * max(idf, 0.1)  # 防止 idf 为负

    # 归一化 W_base 到 [0, 1]
    max_wb = max(w_base.values()) if w_base else 1.0
    if max_wb > 0:
        w_base = {k: v / max_wb for k, v in w_base.items()}

    print(f"  Need W_base（归一化）:")
    for need_name, wb in sorted(w_base.items(), key=lambda x: -x[1]):
        print(f"    {need_name:<25s}  W_base={wb:.4f}")

    # ── 竞争力层：读取品牌-Need 系数 C(brand, need) ──────────────────────────
    # 若品牌未指定或配置表中无对应记录，默认 1.0（中性）
    competitiveness: dict[str, float] = {}
    if brand:
        rows_c = con.execute(
            "SELECT need_name, score FROM brand_need_competitiveness WHERE brand=?",
            (brand,)
        ).fetchall()
        competitiveness = {r[0]: float(r[1]) for r in rows_c}
        # 对图中存在但表中没有记录的 Need，自动补 1.0 并写入（下次可手动更新）
        all_needs = list(need_tgi_sum.keys())
        missing = [n for n in all_needs if n not in competitiveness]
        if missing:
            now_str_c = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            con.executemany(
                "INSERT OR IGNORE INTO brand_need_competitiveness(brand,need_name,score,updated_at) VALUES(?,?,1.0,?)",
                [(brand, n, now_str_c) for n in missing],
            )
            con.commit()
            for n in missing:
                competitiveness[n] = 1.0
        print(f"  品牌「{brand}」竞争力系数:")
        for need_name in sorted(all_needs):
            c = competitiveness.get(need_name, 1.0)
            print(f"    {need_name:<25s}  C={c:.4f}")
    else:
        # 无品牌视角，全取 1.0
        competitiveness = {n: 1.0 for n in need_tgi_sum}
        print(f"  未指定品牌，竞争力系数全部取 1.0")

    # ── 近线层：计算 S_moment ─────────────────────────────────────────────────
    lambda_decay = math.log(2) / time_decay_halflife_days  # 半衰期对应的衰减系数
    now_ts = datetime.now()

    # 按事件名批量查询所有用户的最新时间
    # event_time 格式为 YYYYMMDDHH（10位）或 YYYYMMDD（8位），取前8位作为日期
    event_names = list({e for e, _, _, _ in triggers_edges})
    print(f"  计算时间衰减（半衰期={time_decay_halflife_days}天，涉及 {len(event_names)} 种事件）...")

    # user_event_latest[event_name][user_id] = days_since
    user_event_days: dict[str, dict[str, float]] = {}
    for evt in event_names:
        rows = con.execute(
            "SELECT user_id, MAX(event_time) FROM user_derived_events WHERE derived_event_type=? GROUP BY user_id",
            (evt,),
        ).fetchall()
        days_map: dict[str, float] = {}
        for uid, ts_str in rows:
            try:
                # event_time 格式：YYYYMMDDHH（10位）或 YYYYMMDD（8位）
                date_str = ts_str[:8]
                event_date = datetime.strptime(date_str, "%Y%m%d")
                days = max((now_ts - event_date).days, 0)
            except Exception:
                days = 30  # 无法解析则按30天前处理
            days_map[uid] = days
        user_event_days[evt] = days_map

    # 遍历所有用户计算 S_moment
    all_users = [r[0] for r in con.execute("SELECT user_id FROM user_profile").fetchall()]
    print(f"  对 {len(all_users):,} 名用户计算 Need 分值...")

    # user_need_raw[user_id][need_name] = raw_score
    user_need_raw: dict[str, dict[str, float]] = {}
    for uid in all_users:
        scores: dict[str, float] = {}
        for event_name, need_name, edge_weight, _ in triggers_edges:
            days_map = user_event_days.get(event_name, {})
            if uid not in days_map:
                continue  # 该用户没有此衍生事件
            days = days_map[uid]
            time_decay = math.exp(-lambda_decay * days)
            c = competitiveness.get(need_name, 1.0)
            contribution = w_base.get(need_name, 0.0) * edge_weight * time_decay * c
            scores[need_name] = scores.get(need_name, 0.0) + contribution
        if scores:
            user_need_raw[uid] = scores

    # ── 在线层：Softmax 归一化 ────────────────────────────────────────────────
    now_str = now_ts.strftime("%Y-%m-%dT%H:%M:%S")
    rows_to_insert: list[tuple] = []

    for uid, scores in user_need_raw.items():
        if not scores:
            continue
        need_names = list(scores.keys())
        raw_vals   = [scores[n] for n in need_names]

        # Softmax（带数值稳定性处理）
        max_val = max(raw_vals)
        exp_vals = [math.exp(v - max_val) for v in raw_vals]
        exp_sum  = sum(exp_vals)
        norm_vals = [e / exp_sum for e in exp_vals]

        dominant_idx = norm_vals.index(max(norm_vals))
        for i, need_name in enumerate(need_names):
            rows_to_insert.append((
                uid, need_name,
                round(raw_vals[i], 6),
                round(norm_vals[i], 6),
                1 if i == dominant_idx else 0,
                now_str,
            ))

    con.executemany(
        "INSERT INTO user_need_scores(user_id,need_name,raw_score,normalized_score,dominant_flag,computed_at)"
        " VALUES(?,?,?,?,?,?)",
        rows_to_insert,
    )
    con.commit()

    total_scored = len(user_need_raw)
    print(f"  ✅ Need 打分完成：{total_scored:,} 名用户有 Need 分值，写入 {len(rows_to_insert):,} 条记录")

    # ── 打印每个 Need 的用户统计 ────────────────────────────────────────────
    print(f"\n  Need 主导分布（dominant_flag=1）:")
    for need_name in sorted(w_base.keys()):
        n_dom = con.execute(
            "SELECT COUNT(*) FROM user_need_scores WHERE need_name=? AND dominant_flag=1",
            (need_name,)
        ).fetchone()[0]
        n_any = con.execute(
            "SELECT COUNT(*) FROM user_need_scores WHERE need_name=?",
            (need_name,)
        ).fetchone()[0]
        avg_norm = con.execute(
            "SELECT AVG(normalized_score) FROM user_need_scores WHERE need_name=?",
            (need_name,)
        ).fetchone()[0] or 0
        print(f"    {need_name:<25s}  主导用户={n_dom:>6,}  有分值用户={n_any:>6,}  avg_norm={avg_norm:.4f}")

    return rows_to_insert


# ─────────────────────────────────────────────────────────────────────────────
# Need 打分系统（规则路径）
# ─────────────────────────────────────────────────────────────────────────────

def compute_need_scores_from_rules(
    con: sqlite3.Connection,
    action_meta: list[dict],
    time_decay_halflife_days: float = 7.0,
) -> list[tuple]:
    """
    基于 user_need_segments（规则路径）计算用户 Need 强度分值，写入 user_need_scores。

    三层公式：
      raw_score = Fulfillment × TimeDecay × Specificity

    ── 层1 Fulfillment（行为满足度）───────────────────────────────────────────
      解析每条 Need 规则引用的 Action 事件列表，查询用户在 user_derived_events 中
      各 Action 的命中次数，与该 Action 的饱和阈值（saturation）比较：
        contribution(action) = min(count / saturation, 1.0)
        Fulfillment = mean(contribution) over all referenced Actions

    ── 层2 TimeDecay（时间衰减）──────────────────────────────────────────────
      取该 Need 所有 Action 中最近一次命中时间：
        TimeDecay = e^{-λ × days_since}，λ = ln2 / halflife_days

    ── 层3 Specificity（稀缺性/IDF）─────────────────────────────────────────
      IDF 思路：覆盖用户越少，Need 越稀缺，本底分越高：
        Specificity = log(N_total / N_need_users)
      性价比这类大众 Need（覆盖80%用户）→ Specificity 低
      越野/6座MPV 这类小众 Need（覆盖5%用户）→ Specificity 高

    ── 归一化（Softmax）──────────────────────────────────────────────────────
      对每个用户，将所有 Need 的 raw_score 做数值稳定 Softmax → normalized_score
      normalized_score 最高的 Need 标记 dominant_flag=1

    参数：
      action_meta: cep_rules.action.json 内容（含 name 和 saturation 字段）
    """
    import rule_expr as _rule_expr
    from ontology import _sep
    _sep("Need 强度打分（规则路径：满足度 × 时间衰减 × IDF → Softmax）")

    # ── 检查前置表 ────────────────────────────────────────────────────────────
    try:
        need_count = con.execute("SELECT COUNT(DISTINCT need_name) FROM user_need_segments").fetchone()[0]
    except Exception:
        print("  ⚠  user_need_segments 表不存在，跳过规则路径打分")
        return []

    if need_count == 0:
        print("  ⚠  user_need_segments 为空，请先运行 rule_import.py --need-rules")
        return []

    # ── 建/重建 user_need_scores 表 ───────────────────────────────────────────
    con.executescript("""
        DROP TABLE IF EXISTS user_need_scores;
        CREATE TABLE user_need_scores (
            user_id          TEXT,
            need_name        TEXT,
            raw_score        REAL,
            normalized_score REAL,
            dominant_flag    INTEGER DEFAULT 0,
            exclusion_flag   INTEGER DEFAULT 0,
            fulfillment      REAL,
            time_decay       REAL,
            specificity      REAL,
            tgi              REAL,
            computed_at      TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_uns_user ON user_need_scores(user_id);
        CREATE INDEX IF NOT EXISTS idx_uns_need  ON user_need_scores(need_name);
    """)

    # ── Action 饱和阈值字典 ───────────────────────────────────────────────────
    # {action_name: saturation}，默认 3
    saturation_map: dict[str, int] = {
        r["name"]: int(r.get("saturation", 3))
        for r in action_meta
        if "name" in r
    }

    # ── 读取所有 Need 及其规则、描述、圈选用户数 ──────────────────────────────
    need_rows = con.execute("""
        SELECT need_name,
               MAX(rule_expr)   AS rule_expr,
               MAX(description) AS description,
               COUNT(user_id)   AS n
        FROM user_need_segments
        GROUP BY need_name
    """).fetchall()

    N_total  = con.execute("SELECT COUNT(*) FROM user_profile").fetchone()[0] or 1
    baseline = con.execute("SELECT AVG(is_lead) FROM user_profile").fetchone()[0] or 1e-9
    now_ts   = datetime.now()
    lambda_  = math.log(2) / time_decay_halflife_days

    print(f"  Need 数: {len(need_rows)}  用户总数: {N_total:,}  半衰期: {time_decay_halflife_days}天")

    # ── 计算每个 Need 的 TGI ──────────────────────────────────────────────────
    need_tgi: dict[str, float] = {}
    for need_name, _, _, _ in need_rows:
        lr = con.execute("""
            SELECT AVG(p.is_lead)
            FROM user_need_segments ns
            JOIN user_profile p ON ns.user_id=p.user_id
            WHERE ns.need_name=?
        """, (need_name,)).fetchone()[0] or 0
        need_tgi[need_name] = lr / baseline * 100 if baseline > 0 else 0

    # ── 层3 Specificity（IDF）────────────────────────────────────────────────
    specificity: dict[str, float] = {}
    for need_name, _, _, n_users in need_rows:
        idf = math.log(N_total / max(n_users, 1))
        specificity[need_name] = max(idf, 0.01)

    # 排雷集合：TGI < 60 的 Need 作为负样本标记
    TGI_POISON  = 60    # 低于此值：毒药，打负分 + exclusion_flag=1
    TGI_MEAT    = 120   # 高于此值：肉
    exclusion_needs: set[str] = {n for n, tgi in need_tgi.items() if tgi < TGI_POISON}

    print(f"\n  Need TGI 分层（肉≥{TGI_MEAT} / 盐{TGI_POISON}~{TGI_MEAT} / 毒药<{TGI_POISON}）：")
    for need_name, _, desc, n_u in sorted(need_rows, key=lambda x: -need_tgi.get(x[0], 0)):
        tgi  = need_tgi[need_name]
        spec = specificity[need_name]
        tag  = "🥩肉" if tgi >= TGI_MEAT else ("🧂盐" if tgi >= TGI_POISON else "☠️毒药(排雷)")
        desc_str = f"  {desc}" if desc else ""
        print(f"    {tag}  {need_name:<40s}  覆盖={n_u:>6,}人  TGI={tgi:>6.0f}  IDF={spec:.3f}{desc_str}")

    # ── 提取每个 Need 引用的 Action 列表 ─────────────────────────────────────
    need_actions: dict[str, list[str]] = {}
    for need_name, rule_expr_str, _, _ in need_rows:
        actions = _rule_expr.extract_event_names(rule_expr_str or "")
        need_actions[need_name] = actions

    # ── 预查询：每个 Action 每个用户的命中次数 & 最近时间 ────────────────────
    # all_actions = 所有 Need 引用的 Action 集合
    all_actions: set[str] = set()
    for actions in need_actions.values():
        all_actions.update(actions)

    # action_user_count[action][user_id] = count
    # action_user_latest[action][user_id] = days_since
    action_user_count:  dict[str, dict[str, int]]   = {}
    action_user_latest: dict[str, dict[str, float]] = {}

    for action in all_actions:
        rows = con.execute("""
            SELECT user_id, COUNT(*) as cnt, MAX(event_time) as latest
            FROM user_derived_events
            WHERE derived_event_type = ?
            GROUP BY user_id
        """, (action,)).fetchall()

        cnt_map:    dict[str, int]   = {}
        latest_map: dict[str, float] = {}
        for uid, cnt, ts in rows:
            cnt_map[uid] = cnt
            try:
                event_date = datetime.strptime(str(ts)[:8], "%Y%m%d")
                days = max((now_ts - event_date).days, 0)
            except Exception:
                days = 30
            latest_map[uid] = days

        action_user_count[action]  = cnt_map
        action_user_latest[action] = latest_map

    # ── 遍历所有 Need 的圈选用户，计算三层分值 ────────────────────────────────
    # user_need_raw[user_id][need_name] = (raw_score, fulfillment, time_decay, spec, tgi, is_exclusion)
    user_need_raw: dict[str, dict[str, tuple]] = {}

    for need_name, _, _, _ in need_rows:
        actions     = need_actions.get(need_name, [])
        spec        = specificity[need_name]
        tgi         = need_tgi[need_name]
        is_exclusion = need_name in exclusion_needs

        uid_rows = con.execute(
            "SELECT user_id FROM user_need_segments WHERE need_name=?", (need_name,)
        ).fetchall()

        for (uid,) in uid_rows:
            if is_exclusion:
                # 毒药 Need：raw_score 取负值（-Specificity），使 Softmax 后权重趋近 0
                raw_score   = -spec
                fulfillment = 0.0
                time_decay  = 0.0
            else:
                # ── Fulfillment ──────────────────────────────────────────────
                if actions:
                    contributions = []
                    for action in actions:
                        cnt = action_user_count.get(action, {}).get(uid, 0)
                        sat = saturation_map.get(action, 3)
                        contributions.append(min(cnt / sat, 1.0))
                    fulfillment = sum(contributions) / len(contributions)
                else:
                    fulfillment = 1.0

                # ── TimeDecay ────────────────────────────────────────────────
                min_days = min(
                    (action_user_latest.get(a, {}).get(uid, 30) for a in actions),
                    default=30,
                )
                time_decay = math.exp(-lambda_ * min_days)
                raw_score  = fulfillment * time_decay * spec

            if uid not in user_need_raw:
                user_need_raw[uid] = {}
            user_need_raw[uid][need_name] = (raw_score, fulfillment, time_decay, spec, tgi, is_exclusion)

    # ── Softmax 归一化 ────────────────────────────────────────────────────────
    now_str = now_ts.strftime("%Y-%m-%dT%H:%M:%S")
    rows_to_insert: list[tuple] = []

    for uid, need_scores in user_need_raw.items():
        need_names = list(need_scores.keys())
        raw_vals   = [need_scores[n][0] for n in need_names]

        max_val  = max(raw_vals)
        exp_vals = [math.exp(v - max_val) for v in raw_vals]
        exp_sum  = sum(exp_vals)
        norm_vals = [e / exp_sum for e in exp_vals]

        # dominant 只在非排雷 Need 中选
        non_excl_indices = [i for i, n in enumerate(need_names) if not need_scores[n][5]]
        if non_excl_indices:
            dominant_idx = max(non_excl_indices, key=lambda i: norm_vals[i])
        else:
            dominant_idx = norm_vals.index(max(norm_vals))

        for i, need_name in enumerate(need_names):
            raw, ful, td, sp, tgi, is_excl = need_scores[need_name]
            rows_to_insert.append((
                uid, need_name,
                round(raw, 6),
                round(norm_vals[i], 6),
                1 if i == dominant_idx else 0,
                1 if is_excl else 0,
                round(ful, 4),
                round(td, 4),
                round(sp, 4),
                round(tgi, 1),
                now_str,
            ))

    con.executemany(
        "INSERT INTO user_need_scores"
        "(user_id,need_name,raw_score,normalized_score,dominant_flag,exclusion_flag,"
        " fulfillment,time_decay,specificity,tgi,computed_at)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        rows_to_insert,
    )
    con.commit()

    total_scored = len(user_need_raw)
    excl_count   = sum(1 for n in exclusion_needs)
    print(f"\n  ✅ 打分完成：{total_scored:,} 名用户有 Need 分值，写入 {len(rows_to_insert):,} 条记录")
    print(f"     其中排雷 Need（TGI<{TGI_POISON}）：{excl_count} 个，打负分 exclusion_flag=1")

    # ── 打印每个 Need 的分布统计 ──────────────────────────────────────────────
    print(f"\n  Need 主导分布（dominant_flag=1）：")
    for need_name, _, desc, n_users in sorted(need_rows, key=lambda x: -need_tgi.get(x[0], 0)):
        tgi  = need_tgi[need_name]
        tag  = "🥩" if tgi >= TGI_MEAT else ("🧂" if tgi >= TGI_POISON else "☠️ ")
        n_dom = con.execute(
            "SELECT COUNT(*) FROM user_need_scores WHERE need_name=? AND dominant_flag=1",
            (need_name,)
        ).fetchone()[0]
        avg_ful = con.execute(
            "SELECT AVG(fulfillment) FROM user_need_scores WHERE need_name=?",
            (need_name,)
        ).fetchone()[0] or 0
        avg_norm = con.execute(
            "SELECT AVG(normalized_score) FROM user_need_scores WHERE need_name=?",
            (need_name,)
        ).fetchone()[0] or 0
        desc_str = f"  {desc}" if desc else ""
        print(
            f"  {tag} {need_name:<40s}  主导={n_dom:>5,}"
            f"  TGI={tgi:>6.0f}  avg满足度={avg_ful:.3f}  avg归一化={avg_norm:.4f}"
            f"  IDF={specificity[need_name]:.3f}{desc_str}"
        )

    return rows_to_insert
