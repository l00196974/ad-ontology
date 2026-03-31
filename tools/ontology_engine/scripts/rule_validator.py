#!/usr/bin/env python3
"""
rule_validator.py — 规则验证流程（验证集）
==========================================

职责（薄入口，逻辑委托各专职模块）：
  1. 加载 confirmed_rules.json（由 rule_miner.py 生成）
  2. 加载验证集数据（data_loader）
  3. 重跑 CEP + 人群规则（analytics）
  4. 逐条验证 TGI，与训练集对比输出泛化性报告
  5. 写入 validation_log.json

用法：
    python3 scripts/rule_validator.py --positive data/pos_val.json --negative data/neg_val.json
    python3 scripts/rule_validator.py --tgi-threshold 130 --positive ... --negative ...
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from datetime import datetime

import config
import analytics
import ontology
from data_loader import load as load_data


# ─────────────────────────────────────────────────────────────────────────────
# 验证流程
# ─────────────────────────────────────────────────────────────────────────────

def validate(pos_file: str | None, neg_file: str | None, batch_tag: str) -> None:
    # 1. 读取确权规则
    if not os.path.exists(config.CONFIRMED_RULES_PATH):
        print(f"[rule_validator] ❌ 找不到 confirmed_rules.json，请先运行 rule_miner.py")
        return
    with open(config.CONFIRMED_RULES_PATH, encoding="utf-8") as f:
        rules: list[dict] = json.load(f)
    if not rules:
        print("[rule_validator] confirmed_rules.json 为空，无规则可验证")
        return

    ontology._sep(f"规则验证（验证集）— 批次: {batch_tag}")
    print(f"  加载确权规则: {len(rules)} 条")
    print(f"  配置: TGI 阈值={config.TGI_THRESHOLD}")

    # 2. 加载验证集
    con = load_data(pos_file, neg_file, verbose=True)

    # 补充 CEP/Segment 表
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

    baseline_val = con.execute("SELECT AVG(is_lead) FROM user_profile").fetchone()[0] or 0
    total_users  = con.execute("SELECT COUNT(*) FROM user_profile").fetchone()[0]
    print(f"\n  验证集: {total_users:,} 用户，留资基线={baseline_val:.2%}")

    # 3. 重跑 CEP + 人群规则（使用内置规则，与训练集保持一致）
    ontology._sep("流程 0B：CEP 规则引擎")
    cep_rules = analytics.run_cep_rules(con, config.get_builtin_cep_rules())
    ontology._sep("流程 0C：人群规则引擎")
    analytics.run_segment_rules(con, cep_rules)

    # 4. 逐条验证
    ontology._sep("逐条规则验证结果")
    results = []
    stable = drift = failed = invalid = 0

    for rule in rules:
        seg       = rule.get("target_segment", "")
        feat      = rule.get("feature_event", "")
        tgi_train = rule.get("tgi", 0)

        seg_exists = con.execute(
            "SELECT 1 FROM user_segments WHERE segment=? LIMIT 1", (seg,)
        ).fetchone()

        if not seg_exists:
            status  = "INVALID"
            tgi_val = 0.0
            n_val   = 0
            lr_val  = 0.0
            invalid += 1
        else:
            tgi_val      = round(analytics.compute_tgi(con, seg, feat), 1)
            n_val, lr_val = analytics.seg_stats(con, seg)
            delta = tgi_val - tgi_train
            if tgi_val >= config.TGI_THRESHOLD:
                if abs(delta) <= 20:
                    status = "STABLE"
                    stable += 1
                else:
                    status = "DRIFT"
                    drift += 1
            else:
                status = "FAILED"
                failed += 1

        icon = {"STABLE": "✅", "DRIFT": "⚠ ", "FAILED": "❌", "INVALID": "🚫"}[status]
        print(f"  {icon} [{rule['id']}] {rule.get('description','')}")
        print(f"       路径: {rule.get('source_node','')} --[{rule.get('edge_type','')}]--> {rule.get('target_node','')}")
        print(f"       训练TGI={tgi_train:.1f}  验证TGI={tgi_val:.1f}  "
              f"Δ={tgi_val-tgi_train:+.1f}  人群={n_val:,}人  状态={status}")

        results.append({
            "id":             rule["id"],
            "description":    rule.get("description", ""),
            "source_node":    rule.get("source_node", ""),
            "target_node":    rule.get("target_node", ""),
            "edge_type":      rule.get("edge_type", ""),
            "target_segment": seg,
            "feature_event":  feat,
            "tgi_train":      tgi_train,
            "tgi_val":        tgi_val,
            "delta":          round(tgi_val - tgi_train, 1),
            "seg_count_val":  n_val,
            "lead_rate_val":  round(lr_val, 4),
            "status":         status,
        })

    # 5. 汇总
    ontology._sep("验证汇总")
    total = len(results)
    print(f"  规则总数:  {total}")
    print(f"  ✅ 稳定:   {stable}  ({stable/total:.0%})" if total else "  规则总数: 0")
    print(f"  ⚠  漂移:   {drift}   ({drift/total:.0%})" if total else "")
    print(f"  ❌ 失效:   {failed} ({failed/total:.0%})" if total else "")
    print(f"  🚫 无效:   {invalid} ({invalid/total:.0%})" if total else "")
    print(f"\n  验证集留资基线: {baseline_val:.2%}")

    # 6. 写入验证日志（追加）
    log: list[dict] = []
    if os.path.exists(config.VALIDATION_LOG_PATH):
        with open(config.VALIDATION_LOG_PATH, encoding="utf-8") as f:
            log = json.load(f)
    log.append({
        "batch":       batch_tag,
        "timestamp":   datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "total_users": total_users,
        "baseline":    round(baseline_val, 4),
        "tgi_threshold": config.TGI_THRESHOLD,
        "summary":     {"stable": stable, "drift": drift, "failed": failed, "invalid": invalid},
        "results":     results,
    })
    with open(config.VALIDATION_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    print(f"\n  验证日志已写入: {config.VALIDATION_LOG_PATH}")
    ontology._sep()


# ─────────────────────────────────────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="规则验证（验证集泛化性检验）")
    ap.add_argument("--positive",      default=None, help="验证集正样本 JSON")
    ap.add_argument("--negative",      default=None, help="验证集负样本 JSON")
    ap.add_argument("--batch",         default=None, help="批次标记")
    ap.add_argument("--tgi-threshold", type=int, default=None, help="TGI 阈值覆盖")
    args = ap.parse_args()

    config.apply_overrides(tgi_threshold=args.tgi_threshold)

    batch_tag = args.batch or (os.path.basename(args.positive) if args.positive else "val")
    validate(args.positive, args.negative, batch_tag)


if __name__ == "__main__":
    main()
