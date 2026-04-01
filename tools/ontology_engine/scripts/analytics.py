#!/usr/bin/env python3
"""
analytics.py — 分析层
======================

职责：
  - TGI 计算：compute_tgi / seg_stats
  - CEP 规则引擎：run_cep_rules（执行规则列表，写入 user_derived_events）
  - 人群规则引擎：run_segment_rules（写入 user_segments）
  - 因果检验：causal_check（有/无事件留资率对比 + 控制变量检验）
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime
from typing import TYPE_CHECKING

import config

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

    for rule in rules:
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
            lr = con.execute("""
                SELECT AVG(p.is_lead) FROM user_derived_events d
                JOIN user_profile p ON d.user_id=p.user_id WHERE d.derived_event_type=?
            """, (name,)).fetchone()[0] or 0
            tgi = lr / baseline * 100 if baseline > 0 else 0
            print(f"\r  {name:<28s} {n:>8,} 用户  留资率={lr:.2%}  TGI={tgi:.0f}  {desc}")
            used_rules.append(rule)
        except Exception as e:
            print(f"\r  {name:<28s} SQL执行失败: {e}")

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
