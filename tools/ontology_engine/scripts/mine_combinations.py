#!/usr/bin/env python3
"""
mine_combinations.py — 决策树挖掘高 TGI 行为组合
===================================================

原理：
  1. 从 user_raw_events 聚合出每用户的行为特征向量（各事件类型的次数、天数等）
  2. 训练决策树（target = is_lead），树的每条根→叶路径 = 一个行为组合规则
  3. 按叶节点 TGI 排序，输出 Top-N 组合及对应的 rule_expr 表达式

用法：
  cd tools/ontology_engine
  python3 scripts/mine_combinations.py --db data/cache.db
  python3 scripts/mine_combinations.py --db data/cache.db --top 30 --min-coverage 50
  python3 scripts/mine_combinations.py --db data/cache.db --output data/mined_rules.json
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections import defaultdict

import numpy as np
import pandas as pd
from sklearn.tree import DecisionTreeClassifier, _tree

sys.path.insert(0, os.path.dirname(__file__))
import config


# ── 不参与特征的事件类型 ────────────────────────────────────────────────────
_EXCLUDE_EVENTS = {"lead_submit", "unknown"}


# ─────────────────────────────────────────────────────────────────────────────
# 步骤 1：从 DB 构建用户特征矩阵
# ─────────────────────────────────────────────────────────────────────────────

def build_feature_matrix(con: sqlite3.Connection) -> pd.DataFrame:
    """
    从 user_raw_events 聚合出每用户的特征向量。

    特征维度：
      {event_type}_count   — 该事件发生次数
      {event_type}_days    — 该事件跨越的不同日期数
      {event_type}_dur_max — 该事件单次最长停留秒数
      brand_diversity      — 用户涉及的不同品牌数（search+detail+loan）
      model_diversity      — 用户涉及的不同车型数
      event_type_count     — 用户行为覆盖的事件类型数（广度）
      total_actions        — 总行为次数
    """
    print("  [1/4] 聚合用户行为特征...")

    # 基础聚合：每用户每事件 count / days / dur_max
    rows = con.execute("""
        SELECT user_id, event_type,
               COUNT(*)                        AS cnt,
               COUNT(DISTINCT time_str)        AS days,
               MAX(COALESCE(dur_time, 0))      AS dur_max,
               SUM(COALESCE(dur_time, 0))      AS dur_sum
        FROM user_raw_events
        WHERE event_type != 'lead_submit'
          AND event_type != 'unknown'
        GROUP BY user_id, event_type
    """).fetchall()

    # pivot：user_id → dict of features
    feat: dict[str, dict] = defaultdict(dict)
    event_types: set[str] = set()
    for uid, etype, cnt, days, dur_max, dur_sum in rows:
        feat[uid][f"{etype}_count"]   = cnt
        feat[uid][f"{etype}_days"]    = days
        feat[uid][f"{etype}_dur_max"] = round(dur_max, 1)
        event_types.add(etype)

    # 品牌 / 车型多样性
    brand_rows = con.execute("""
        SELECT user_id, COUNT(DISTINCT json_extract(attr_json, '$.brand')) brand_div
        FROM user_raw_events
        WHERE event_type IN ('search_vertical','search_general','view_car_detail',
                             'view_loan_calc','view_car_compare','view_floor_price')
          AND json_extract(attr_json, '$.brand') IS NOT NULL
        GROUP BY user_id
    """).fetchall()
    for uid, bdiv in brand_rows:
        feat[uid]["brand_diversity"] = bdiv

    model_rows = con.execute("""
        SELECT user_id, COUNT(DISTINCT json_extract(attr_json, '$.model')) model_div
        FROM user_raw_events
        WHERE event_type IN ('view_car_detail', 'view_loan_calc', 'search_entertainment')
          AND json_extract(attr_json, '$.model') IS NOT NULL
        GROUP BY user_id
    """).fetchall()
    for uid, mdiv in model_rows:
        feat[uid]["model_diversity"] = mdiv

    # 行为广度（事件类型数）和总行为次数
    breadth_rows = con.execute("""
        SELECT user_id,
               COUNT(DISTINCT event_type) type_count,
               COUNT(*)                   total_actions
        FROM user_raw_events
        WHERE event_type != 'lead_submit' AND event_type != 'unknown'
        GROUP BY user_id
    """).fetchall()
    for uid, tc, ta in breadth_rows:
        feat[uid]["event_type_count"] = tc
        feat[uid]["total_actions"]    = ta

    # 用户标签
    profile_rows = con.execute(
        "SELECT user_id, is_lead FROM user_profile"
    ).fetchall()

    print(f"  [1/4] 完成：{len(profile_rows):,} 用户，{len(event_types)} 种事件类型")

    # 构建 DataFrame
    records = []
    for uid, is_lead in profile_rows:
        row = {"user_id": uid, "is_lead": is_lead}
        row.update(feat.get(uid, {}))
        records.append(row)

    df = pd.DataFrame(records).fillna(0)
    df = df.set_index("user_id")
    return df, sorted(event_types)


# ─────────────────────────────────────────────────────────────────────────────
# 步骤 2：训练决策树
# ─────────────────────────────────────────────────────────────────────────────

def train_tree(df: pd.DataFrame, max_depth: int = 6, min_samples_leaf: int = 30) -> tuple:
    """训练决策树，返回 (tree, feature_names, X, y)"""
    print(f"  [2/4] 训练决策树（max_depth={max_depth}, min_leaf={min_samples_leaf}）...")

    target = "is_lead"
    feature_cols = [c for c in df.columns if c != target]

    X = df[feature_cols].values.astype(np.float32)
    y = df[target].values.astype(np.int32)

    clf = DecisionTreeClassifier(
        max_depth=max_depth,
        min_samples_leaf=min_samples_leaf,
        class_weight="balanced",   # 正负样本不平衡时自动加权
        random_state=42,
    )
    clf.fit(X, y)

    n_leaves = clf.get_n_leaves()
    print(f"  [2/4] 完成：{n_leaves} 个叶子节点，特征数={len(feature_cols)}")
    return clf, feature_cols, X, y


# ─────────────────────────────────────────────────────────────────────────────
# 步骤 3：提取所有根→叶路径并计算 TGI
# ─────────────────────────────────────────────────────────────────────────────

def extract_rules(
    clf: DecisionTreeClassifier,
    feature_names: list[str],
    X: np.ndarray,
    y: np.ndarray,
    baseline_lr: float,
    min_coverage: int = 30,
) -> list[dict]:
    """
    遍历决策树，提取每条根→叶路径，计算该路径上：
      - coverage：命中用户数
      - lead_rate：留资率
      - tgi：TGI = lead_rate / baseline_lr × 100
      - conditions：路径条件列表（feature, op, threshold）
    """
    print("  [3/4] 提取规则路径...")

    tree = clf.tree_
    results = []

    def _traverse(node_id: int, path: list[tuple]):
        """递归遍历树节点"""
        # 叶子节点
        if tree.children_left[node_id] == _tree.TREE_LEAF:
            # 获取该叶子的样本（通过 decision_path）
            node_indicator = clf.decision_path(X)
            # 命中该叶子的样本掩码
            leaf_ids = clf.apply(X)
            mask = leaf_ids == node_id
            n = mask.sum()
            if n < min_coverage:
                return
            lr = y[mask].mean()
            tgi = lr / baseline_lr * 100 if baseline_lr > 0 else 0
            if tgi < 80:  # 过滤掉明显低价值的路径
                return
            results.append({
                "conditions": list(path),
                "coverage":   int(n),
                "lead_rate":  round(float(lr), 4),
                "tgi":        round(tgi, 1),
            })
            return

        # 内部节点：获取分裂特征和阈值
        feat_idx = tree.feature[node_id]
        threshold = tree.threshold[node_id]
        feat_name = feature_names[feat_idx]

        # 左子树：feature <= threshold
        _traverse(
            tree.children_left[node_id],
            path + [(feat_name, "<=", threshold)]
        )
        # 右子树：feature > threshold
        _traverse(
            tree.children_right[node_id],
            path + [(feat_name, ">", threshold)]
        )

    _traverse(0, [])
    results.sort(key=lambda x: x["tgi"], reverse=True)
    print(f"  [3/4] 完成：找到 {len(results)} 条有效路径（coverage >= {min_coverage}）")
    return results


# ─────────────────────────────────────────────────────────────────────────────
# 步骤 4：将路径翻译成 rule_expr 表达式
# ─────────────────────────────────────────────────────────────────────────────

def _threshold_to_int(val: float) -> int:
    """决策树阈值是连续值，转成整数规则阈值（向上取整到最近整数边界）"""
    return max(1, int(val) + 1)


def path_to_rule_expr(conditions: list[tuple]) -> str | None:
    """
    将决策树路径条件转换为 rule_expr 表达式。

    特征命名规则：
      {event_type}_count   → raw.{event_type}.count >= N  或  NOT raw.{event_type}.exists
      {event_type}_days    → raw.{event_type}.days >= N
      {event_type}_dur_max → raw.{event_type}.dur_max >= N
      brand_diversity      → raw.search_vertical[brand].distinct >= N
      model_diversity      → raw.view_car_detail[model].distinct >= N
      event_type_count     → (无直接对应，跳过)
      total_actions        → (无直接对应，跳过)
    """
    clauses = []
    for feat, op, thr in conditions:
        thr_i = _threshold_to_int(thr)
        thr_f = round(thr, 1)

        # 正向条件（> threshold → 发生了该行为）
        if op == ">":
            if feat.endswith("_count"):
                etype = feat[:-6]
                if thr_i <= 1:
                    clauses.append(f"raw.{etype}.exists")
                else:
                    clauses.append(f"raw.{etype}.count >= {thr_i}")
            elif feat.endswith("_days"):
                etype = feat[:-5]
                clauses.append(f"raw.{etype}.days >= {thr_i}")
            elif feat.endswith("_dur_max"):
                etype = feat[:-8]
                clauses.append(f"raw.{etype}.dur_max >= {thr_f}")
            elif feat == "brand_diversity":
                clauses.append(f"raw.search_vertical[brand].distinct >= {thr_i}")
            elif feat == "model_diversity":
                clauses.append(f"raw.view_car_detail[model].distinct >= {thr_i}")
            # event_type_count / total_actions 暂不翻译（无直接语法）

        # 负向条件（<= threshold → 未发生或次数少）
        else:  # op == "<="
            if feat.endswith("_count") and thr < 0.5:
                etype = feat[:-6]
                clauses.append(f"NOT raw.{etype}.exists")
            # 其他 <= 条件通常是"行为不够多"，对挖掘意义不大，跳过

    if not clauses:
        return None
    return " AND ".join(clauses)


# ─────────────────────────────────────────────────────────────────────────────
# 步骤 5：特征重要性汇总
# ─────────────────────────────────────────────────────────────────────────────

def print_feature_importance(clf, feature_names: list[str], top_n: int = 20) -> None:
    importances = clf.feature_importances_
    idx = np.argsort(importances)[::-1][:top_n]
    print(f"\n{'─'*60}")
    print(f"  Top-{top_n} 特征重要性（决策树分裂贡献度）")
    print(f"{'─'*60}")
    for rank, i in enumerate(idx, 1):
        if importances[i] < 0.001:
            break
        print(f"  {rank:>3}. {feature_names[i]:<35s}  {importances[i]:.4f}")


# ─────────────────────────────────────────────────────────────────────────────
# 打印 & 输出
# ─────────────────────────────────────────────────────────────────────────────

def print_top_rules(rules: list[dict], top_n: int, baseline_lr: float) -> None:
    sep = "─" * 70
    print(f"\n{sep}")
    print(f"  Top-{top_n} 高 TGI 行为组合")
    print(f"  全量留资基线: {baseline_lr:.2%}")
    print(sep)

    shown = 0
    for i, r in enumerate(rules):
        expr = path_to_rule_expr(r["conditions"])
        if not expr:
            continue
        tag = "🥩肉" if r["tgi"] >= 120 else "🧂盐"
        print(f"\n  #{i+1}  {tag}  TGI={r['tgi']:.0f}  "
              f"覆盖={r['coverage']:,}人  留资率={r['lead_rate']:.2%}")
        print(f"       规则: {expr}")
        # 打印原始条件（方便理解）
        cond_strs = [f"{f} {op} {v:.2f}" for f, op, v in r["conditions"]]
        print(f"       条件: {' & '.join(cond_strs)}")
        shown += 1
        if shown >= top_n:
            break


def save_rules(rules: list[dict], baseline_lr: float, output_path: str) -> None:
    """保存为可直接用于 rule_import.py 的 JSON 格式"""
    out = []
    for r in rules:
        expr = path_to_rule_expr(r["conditions"])
        if not expr:
            continue
        # 生成规则名（取前两个正向条件的事件名拼接）
        pos_feats = [f for f, op, _ in r["conditions"] if op == ">"]
        name_parts = []
        for feat in pos_feats[:2]:
            for suffix in ("_count", "_days", "_dur_max"):
                if feat.endswith(suffix):
                    name_parts.append(feat[:-len(suffix)])
                    break
        rule_name = "mined_" + "_x_".join(name_parts) if name_parts else f"mined_{len(out)+1}"

        out.append({
            "name":       rule_name,
            "desc":       f"决策树挖掘 TGI={r['tgi']:.0f} 覆盖={r['coverage']}",
            "rule":       expr,
            "tgi":        r["tgi"],
            "coverage":   r["coverage"],
            "lead_rate":  r["lead_rate"],
            "baseline_lr": round(baseline_lr, 4),
        })

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n  [输出] 已保存 {len(out)} 条规则到 {output_path}")


# ─────────────────────────────────────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description="决策树挖掘高 TGI 行为组合",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--db",           required=True,       help="SQLite 数据库路径")
    ap.add_argument("--top",          type=int, default=20, help="打印 Top-N 规则（默认20）")
    ap.add_argument("--max-depth",    type=int, default=6,  help="决策树最大深度（默认6）")
    ap.add_argument("--min-coverage", type=int, default=50, help="最小覆盖人数（默认50）")
    ap.add_argument("--output",       default=None,         help="输出 JSON 路径（可选）")
    ap.add_argument("--importance",   action="store_true",  help="打印特征重要性")
    args = ap.parse_args()

    if not os.path.exists(args.db):
        print(f"❌ 数据库不存在: {args.db}")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  决策树行为组合挖掘")
    print(f"  DB: {args.db}")
    print(f"{'='*60}\n")

    con = sqlite3.connect(args.db)
    baseline_lr = con.execute("SELECT AVG(is_lead) FROM user_profile").fetchone()[0] or 0
    print(f"  全量留资基线: {baseline_lr:.2%}")

    # 构建特征矩阵
    df, event_types = build_feature_matrix(con)
    print(f"  特征矩阵: {df.shape[0]:,} 行 × {df.shape[1]} 列")
    print(f"  正样本: {df['is_lead'].sum():,}  负样本: {(df['is_lead']==0).sum():,}")

    # 训练决策树
    clf, feature_names, X, y = train_tree(
        df,
        max_depth=args.max_depth,
        min_samples_leaf=args.min_coverage,
    )

    # 特征重要性
    if args.importance:
        print_feature_importance(clf, feature_names)

    # 提取规则路径
    rules = extract_rules(clf, feature_names, X, y, baseline_lr, args.min_coverage)

    # 打印 Top-N
    print_top_rules(rules, args.top, baseline_lr)

    # 输出 JSON
    if args.output:
        save_rules(rules, baseline_lr, args.output)
    else:
        default_out = os.path.join(os.path.dirname(args.db), "mined_rules.json")
        save_rules(rules, baseline_lr, default_out)

    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    main()
