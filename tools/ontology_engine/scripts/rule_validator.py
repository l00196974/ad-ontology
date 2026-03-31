#!/usr/bin/env python3
"""
rule_validator.py — 规则验证模块（验证集）
==========================================

职责：
  1. 加载 confirmed_rules.json（由 rule_miner.py 生成）
  2. 调用 data_loader.load() 加载新一批数据（验证集）
  3. 在验证集上重跑 CEP 规则 + 人群规则
  4. 对每条确权规则重新计算 TGI，与训练集 TGI 对比
  5. 输出泛化性报告：稳定/漂移/失效

用法：
    python3 scripts/rule_validator.py --positive data/pos_val.json --negative data/neg_val.json
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from datetime import datetime

from data_loader import load
from rule_miner import (
    CEP_RULES,
    SEGMENT_RULES,
    TGI_THRESHOLD,
    run_cep_rules,
    run_segment_rules,
    _sep,
)

_SCRIPT_DIR     = os.path.dirname(os.path.abspath(__file__))
CONFIRMED_RULES = os.path.join(_SCRIPT_DIR, "confirmed_rules.json")
VALIDATION_LOG  = os.path.join(_SCRIPT_DIR, "validation_log.json")


# ─────────────────────────────────────────────────────────────────────────────
# 对单条规则在验证集上计算 TGI
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


def _seg_stats(con: sqlite3.Connection, segment: str) -> tuple[int, float]:
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
# 主验证流程
# ─────────────────────────────────────────────────────────────────────────────

def validate(pos_file: str | None, neg_file: str | None, batch_tag: str) -> None:
    # 1. 读取确权规则
    if not os.path.exists(CONFIRMED_RULES):
        print(f"[rule_validator] ❌ 找不到 confirmed_rules.json，请先运行 rule_miner.py")
        return
    with open(CONFIRMED_RULES, encoding="utf-8") as f:
        rules: list[dict] = json.load(f)
    if not rules:
        print("[rule_validator] confirmed_rules.json 为空，无规则可验证")
        return

    _sep(f"规则验证（验证集）— 批次: {batch_tag}")
    print(f"  加载确权规则: {len(rules)} 条")

    # 2. 加载验证集
    con = load(pos_file, neg_file, verbose=True)
    baseline_val = con.execute("SELECT AVG(is_lead) FROM user_profile").fetchone()[0] or 0
    total_users  = con.execute("SELECT COUNT(*) FROM user_profile").fetchone()[0]
    print(f"\n  验证集: {total_users:,} 用户，留资基线={baseline_val:.2%}")

    # 3. 重跑 CEP + 人群规则
    run_cep_rules(con)
    run_segment_rules(con)

    # 4. 逐条验证
    _sep("逐条规则验证结果")
    results = []
    stable = drift = invalid = 0

    for rule in rules:
        seg      = rule.get("target_segment", "")
        feat     = rule.get("feature_event", "")
        tgi_train = rule.get("tgi", 0)

        # 检查 segment 是否在验证集中存在
        seg_exists = con.execute(
            "SELECT 1 FROM user_segments WHERE segment=? LIMIT 1", (seg,)
        ).fetchone()
        if not seg_exists:
            status = "INVALID"
            tgi_val = 0.0
            n_val   = 0
            lr_val  = 0.0
            invalid += 1
        else:
            tgi_val = round(_compute_tgi(con, seg, feat), 1)
            n_val, lr_val = _seg_stats(con, seg)

            # 判断稳定性
            delta = tgi_val - tgi_train
            if tgi_val >= TGI_THRESHOLD:
                if abs(delta) <= 20:
                    status = "STABLE"   # TGI 仍在阈值以上且变化不大
                    stable += 1
                else:
                    status = "DRIFT"    # TGI 超阈值但变化较大（需关注）
                    drift += 1
            else:
                status = "FAILED"       # TGI 跌破阈值，规则失效
                invalid += 1

        icon = {"STABLE": "✅", "DRIFT": "⚠ ", "FAILED": "❌", "INVALID": "🚫"}[status]
        print(f"  {icon} [{rule['id']}] {rule['description']}")
        print(f"       路径: {rule['source_node']} --[{rule['edge_type']}]--> {rule['target_node']}")
        print(f"       训练TGI={tgi_train:.1f}  验证TGI={tgi_val:.1f}  "
              f"Δ={tgi_val-tgi_train:+.1f}  人群={n_val:,}人  状态={status}")

        results.append({
            "id":           rule["id"],
            "description":  rule["description"],
            "source_node":  rule["source_node"],
            "target_node":  rule["target_node"],
            "edge_type":    rule["edge_type"],
            "target_segment": seg,
            "feature_event": feat,
            "tgi_train":    tgi_train,
            "tgi_val":      tgi_val,
            "delta":        round(tgi_val - tgi_train, 1),
            "seg_count_val": n_val,
            "lead_rate_val": round(lr_val, 4),
            "status":       status,
        })

    # 5. 汇总
    _sep("验证汇总")
    total = len(results)
    print(f"  规则总数:  {total}")
    print(f"  ✅ 稳定:   {stable}  ({stable/total:.0%})")
    print(f"  ⚠  漂移:   {drift}   ({drift/total:.0%})")
    print(f"  ❌ 失效:   {invalid} ({invalid/total:.0%})")
    print(f"\n  验证集留资基线: {baseline_val:.2%}")

    # 6. 写入验证日志（追加）
    log: list[dict] = []
    if os.path.exists(VALIDATION_LOG):
        with open(VALIDATION_LOG, encoding="utf-8") as f:
            log = json.load(f)
    log.append({
        "batch":      batch_tag,
        "timestamp":  datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "total_users": total_users,
        "baseline":   round(baseline_val, 4),
        "summary":    {"stable": stable, "drift": drift, "invalid": invalid},
        "results":    results,
    })
    with open(VALIDATION_LOG, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    print(f"\n  验证日志已写入: {VALIDATION_LOG}")
    _sep()


# ─────────────────────────────────────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="规则验证（验证集泛化性检验）")
    ap.add_argument("--positive", default=None, help="验证集正样本 JSON")
    ap.add_argument("--negative", default=None, help="验证集负样本 JSON")
    ap.add_argument("--batch",    default=None, help="批次标记")
    args = ap.parse_args()

    batch_tag = args.batch or (os.path.basename(args.positive) if args.positive else "val")
    validate(args.positive, args.negative, batch_tag)
