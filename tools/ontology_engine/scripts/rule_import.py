#!/usr/bin/env python3
"""
rule_import.py — 人工规则导入 & 验证工具
==========================================

CEP 规则和 Need 圈选规则均使用规则表达式（rule_expr.py），不再用 SQL。

用法：
    python3 scripts/rule_import.py --db data/cache.db --cep-rules data/my_cep.json
    python3 scripts/rule_import.py --db data/cache.db --need-rules data/my_need.json
    python3 scripts/rule_import.py --db data/cache.db --cep-rules ... --dry-run
    python3 scripts/rule_import.py --db data/cache.db --cep-rules ... --force

─────────────────────────────────────────────────────────────
CEP 规则文件格式（JSON 数组，rule 字段用 raw.* 语法）：
[
  {"name": "brand_focus_3plus",    "desc": "垂媒品牌搜索>=3次",
   "rule": "raw.search_vertical[brand!=null].count >= 3"},
  {"name": "detail_loan_same_brand","desc": "同品牌详情+车贷",
   "rule": "raw.view_car_detail[brand].same.raw.view_loan_calc[brand].exists"},
  {"name": "multi_brand_search",   "desc": "搜索>=3个不同品牌",
   "rule": "raw.search_vertical[brand].distinct >= 3"},
  {"name": "search_before_detail", "desc": "先搜索后看详情",
   "rule": "raw.search_vertical.before.view_car_detail.exists"}
]

Need 圈选规则文件格式（JSON 数组，rule 字段用 event.*/profile.* 语法）：
[
  {"need_name": "金融方案需求", "description": "...",
   "rule": "event.view_loan_calc.exists AND event.view_car_detail.count >= 1",
   "weight": 0.9}
]

规则表达式完整语法参见 rule_expr.py。
─────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime

import networkx as nx

import config
import analytics
import ontology
import rule_expr
import bitmap_engine as bm_eng


# ─────────────────────────────────────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────────────────────────────────────

def _load_json_file(path: str) -> list[dict]:
    if not os.path.exists(path):
        print(f"  ❌ 文件不存在: {path}")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        print(f"  ❌ 文件格式错误（应为 JSON 数组）: {path}")
        sys.exit(1)
    return data


def _get_existing_cep_names(con: sqlite3.Connection) -> set[str]:
    rows = con.execute(
        "SELECT DISTINCT derived_event_type FROM user_derived_events"
    ).fetchall()
    return {r[0] for r in rows}


def _get_existing_need_names(con: sqlite3.Connection) -> set[str]:
    try:
        rows = con.execute("SELECT DISTINCT need_name FROM user_need_segments").fetchall()
        return {r[0] for r in rows}
    except Exception:
        return set()


def _print_summary(label: str, accepted: list, rejected: list, skipped: list) -> None:
    print(f"\n  ─── {label} 导入汇总 ───")
    print(f"  ✅ 接受: {len(accepted)} 条  ❌ 拒绝: {len(rejected)} 条  ⏭  跳过: {len(skipped)} 条")
    if rejected:
        print(f"\n  拒绝详情：")
        for r in rejected:
            name = r.get("need_name") or r.get("name") or r.get("id", "?")
            print(f"    [{name}] {r.get('reason', '')}")


# ─────────────────────────────────────────────────────────────────────────────
# CEP 规则导入（规则表达式 → user_derived_events）
# ─────────────────────────────────────────────────────────────────────────────

def import_cep_rules(
    con: sqlite3.Connection,
    rules: list[dict],
    force: bool = False,
    dry_run: bool = False,
    min_user_count: int = 10,
    ctx: bm_eng.BitmapContext | None = None,
) -> dict:
    """
    导入并验证 CEP 规则。规则格式：{name, desc, rule}
    rule 使用 raw.* 表达式语法（见 rule_expr.py）。

    验证项：
      1. rule 语法检查
      2. 执行后用户数 >= min_user_count（拦截）
      3. TGI >= config.TGI_THRESHOLD（警告，不拦截）

    成功则将命中用户写入 user_derived_events（derived_event_type = name）。
    返回 {"accepted": [...], "rejected": [...], "skipped": [...]}
    """
    ontology._sep(f"CEP 规则导入（共 {len(rules)} 条，force={force}，dry_run={dry_run}）")

    existing_names = _get_existing_cep_names(con) if not force else set()
    baseline = con.execute("SELECT AVG(is_lead) FROM user_profile").fetchone()[0] or 0
    now_str  = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    accepted: list[dict] = []
    rejected: list[dict] = []
    skipped:  list[str]  = []

    # 一次性初始化 BitmapContext，整批规则共享缓存；外部传入则复用（跨 CEP+Need 共享）
    ctx = ctx or bm_eng.BitmapContext(con)

    for item in rules:
        name = item.get("name", "").strip()
        desc = item.get("desc", "")
        expr = item.get("rule", "").strip()

        if not name or not expr:
            rejected.append({"name": name or "?", "desc": desc,
                             "reason": "缺少 name 或 rule 字段"})
            print(f"  ❌ [?] 缺少 name 或 rule: {item}")
            continue

        # 增量检查
        if name in existing_names and not force:
            skipped.append(name)
            print(f"  ⏭  [{name}] 已存在，跳过（--force 可强制重跑）")
            continue

        # 语法检查
        ok, err = rule_expr.validate_expr(expr)
        if not ok:
            rejected.append({"name": name, "desc": desc, "reason": f"表达式语法错误: {err}"})
            print(f"  ❌ [{name}] 语法错误: {err}")
            continue

        if dry_run:
            print(f"  🔍 [{name}] dry-run 语法通过（未执行）")
            accepted.append({"name": name, "desc": desc, "dry_run": True})
            continue

        # 执行表达式 → bitmap → user_id 列表
        print(f"  {name:<30s} → 圈选中...", end="", flush=True)
        try:
            bm      = ctx.eval_expr(expr)
            matched = ctx.to_user_set(bm)
        except Exception as e:
            rejected.append({"name": name, "desc": desc, "reason": f"表达式执行失败: {e}"})
            print(f"\r  ❌ [{name}] 执行失败: {e}")
            continue

        n = ctx.popcount(bm)
        if n < min_user_count:
            rejected.append({"name": name, "desc": desc,
                             "reason": f"用户数={n} < {min_user_count}，规则可能过严"})
            print(f"\r  ❌ [{name}] 用户={n:,}  规则过严，拒绝")
            continue

        # force 时先清除旧数据
        if force and name in existing_names:
            con.execute("DELETE FROM user_derived_events WHERE derived_event_type=?", (name,))
            con.commit()

        # 写入 user_derived_events（每个命中用户写一条记录）
        con.executemany(
            "INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)"
            " VALUES(?,?,?,?,?)",
            [(uid, now_str, name, expr, "{}") for uid in matched]
        )
        con.commit()

        # 计算 TGI
        lr = con.execute("""
            SELECT AVG(p.is_lead) FROM user_derived_events d
            JOIN user_profile p ON d.user_id=p.user_id WHERE d.derived_event_type=?
        """, (name,)).fetchone()[0] or 0
        tgi = lr / baseline * 100 if baseline > 0 else 0

        warnings = []
        if tgi < config.TGI_THRESHOLD:
            warnings.append(f"TGI={tgi:.0f} 低于阈值 {config.TGI_THRESHOLD}")

        result = {"name": name, "desc": desc, "user_count": n,
                  "lead_rate": round(lr, 4), "tgi": round(tgi, 1), "warnings": warnings}
        accepted.append(result)
        tgi_flag = "✅" if tgi >= config.TGI_THRESHOLD else "⚠ "
        warn_str = f"  | ⚠  {'; '.join(warnings)}" if warnings else ""
        print(f"\r  {tgi_flag} [{name}] 用户={n:,}  TGI={tgi:.0f}  {desc}{warn_str}")

    _print_summary("CEP", accepted, rejected, skipped)
    return {"accepted": accepted, "rejected": rejected, "skipped": skipped}


# ─────────────────────────────────────────────────────────────────────────────
# Need 圈选规则导入（规则表达式 → user_need_segments）
# ─────────────────────────────────────────────────────────────────────────────

def import_need_rules(
    con: sqlite3.Connection,
    G: nx.DiGraph,
    rules: list[dict],
    force: bool = False,
    dry_run: bool = False,
    min_user_count: int = 10,
    ctx: bm_eng.BitmapContext | None = None,
) -> dict:
    """
    导入并验证 Need 圈选规则。规则格式：{need_name, description, rule, weight}
    rule 使用 event.*/profile.* 表达式语法（见 rule_expr.py）。

    成功则写入 user_need_segments 并更新图谱 Need 节点。
    返回 {"accepted": [...], "rejected": [...], "skipped": [...]}
    """
    ontology._sep(f"Need 圈选规则导入（共 {len(rules)} 条，force={force}，dry_run={dry_run}）")

    con.execute("""
        CREATE TABLE IF NOT EXISTS user_need_segments (
            need_name   TEXT NOT NULL,
            user_id     TEXT NOT NULL,
            rule_expr   TEXT,
            derived_at  TEXT,
            PRIMARY KEY (need_name, user_id)
        )
    """)
    con.commit()

    existing_names = _get_existing_need_names(con) if not force else set()
    baseline = con.execute("SELECT AVG(is_lead) FROM user_profile").fetchone()[0] or 0

    accepted: list[dict] = []
    rejected: list[dict] = []
    skipped:  list[str]  = []

    # 一次性初始化 BitmapContext，整批规则共享缓存；外部传入则复用（跨 CEP+Need 共享）
    ctx = ctx or bm_eng.BitmapContext(con)

    for i, item in enumerate(rules):
        rid       = item.get("id") or f"NR{i+1}"
        need_name = item.get("need_name", "").strip()
        expr      = item.get("rule", "").strip()
        desc      = item.get("description", "")
        weight    = float(item.get("weight", 1.0))

        def _reject(reason: str):
            rejected.append({"id": rid, "need_name": need_name,
                             "description": desc, "reason": reason})
            print(f"  ❌ [{rid}] {need_name!r}  拒绝：{reason}")

        if not need_name or not expr:
            _reject("缺少 need_name 或 rule 字段")
            continue

        if need_name in existing_names and not force:
            skipped.append(need_name)
            print(f"  ⏭  [{need_name}] 已存在，跳过（--force 可强制重跑）")
            continue

        ok, err = rule_expr.validate_expr(expr)
        if not ok:
            _reject(f"规则表达式语法错误: {err}")
            continue

        if dry_run:
            print(f"  🔍 [{need_name}] dry-run 语法通过（未执行）")
            accepted.append({"id": rid, "need_name": need_name, "description": desc,
                             "rule": expr, "weight": weight, "dry_run": True})
            continue

        print(f"  {need_name:<25s} → 圈选中...", end="", flush=True)
        try:
            bm      = ctx.eval_expr(expr)
            matched = ctx.to_user_set(bm)
        except Exception as e:
            _reject(f"规则表达式执行失败: {e}")
            print(f"\r  ❌ [{need_name}] 执行失败: {e}")
            continue

        n = ctx.popcount(bm)
        if n < min_user_count:
            _reject(f"圈选用户数={n} < {min_user_count}，规则可能过严")
            print(f"\r  ❌ [{need_name}] 用户={n:,}  规则过严，拒绝")
            continue

        # 计算 TGI
        if matched:
            ph = ",".join("?" * len(matched))
            lr = con.execute(
                f"SELECT AVG(is_lead) FROM user_profile WHERE user_id IN ({ph})",
                list(matched)
            ).fetchone()[0] or 0
        else:
            lr = 0.0
        tgi = lr / baseline * 100 if baseline > 0 else 0

        if force and need_name in existing_names:
            con.execute("DELETE FROM user_need_segments WHERE need_name=?", (need_name,))
            con.commit()

        now_str = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        con.executemany(
            "INSERT OR REPLACE INTO user_need_segments(need_name,user_id,rule_expr,derived_at)"
            " VALUES(?,?,?,?)",
            [(need_name, uid, expr, now_str) for uid in matched]
        )
        con.commit()

        # 更新/创建图谱 Need 节点
        if need_name not in G.nodes:
            ontology.add_node(G, need_name, "Need",
                              user_count=n, lead_rate=round(lr, 4), tgi=round(tgi, 1),
                              rule_expr=expr, weight=weight)
        else:
            G.nodes[need_name].update({"user_count": n, "lead_rate": round(lr, 4),
                                       "tgi": round(tgi, 1), "rule_expr": expr, "weight": weight})

        warnings = []
        if tgi < config.TGI_THRESHOLD:
            warnings.append(f"TGI={tgi:.0f} 低于阈值 {config.TGI_THRESHOLD}")

        result = {"id": rid, "need_name": need_name, "description": desc, "rule": expr,
                  "weight": weight, "user_count": n, "lead_rate": round(lr, 4),
                  "tgi": round(tgi, 1), "warnings": warnings}
        accepted.append(result)
        tgi_flag = "✅" if tgi >= config.TGI_THRESHOLD else "⚠ "
        warn_str = f"  | ⚠  {'; '.join(warnings)}" if warnings else ""
        print(f"\r  {tgi_flag} [{need_name}] 用户={n:,}  TGI={tgi:.0f}  {desc}{warn_str}")

    _print_summary("Need", accepted, rejected, skipped)
    return {"accepted": accepted, "rejected": rejected, "skipped": skipped}


# ─────────────────────────────────────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description="人工规则导入工具 — CEP 规则和 Need 圈选规则均使用表达式语法",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--db",            required=True)
    ap.add_argument("--cep-rules",     default=None, help="CEP 规则 JSON 文件（raw.* 语法）")
    ap.add_argument("--need-rules",    default=None, help="Need 圈选规则 JSON 文件（event.*/profile.* 语法）")
    ap.add_argument("--ontology",      default=None, help="图谱 JSON 文件路径")
    ap.add_argument("--save-ontology", default=None, help="Need 导入后图谱保存路径")
    ap.add_argument("--force",         action="store_true")
    ap.add_argument("--dry-run",       action="store_true")
    ap.add_argument("--min-users",     type=int, default=10)
    ap.add_argument("--tgi-threshold", type=int, default=None)
    args = ap.parse_args()

    if args.tgi_threshold:
        config.apply_overrides(tgi_threshold=args.tgi_threshold)
    if not args.cep_rules and not args.need_rules:
        ap.error("至少指定 --cep-rules 或 --need-rules 之一")
    if not os.path.exists(args.db):
        print(f"❌ 数据库不存在: {args.db}")
        sys.exit(1)

    con = sqlite3.connect(args.db)

    # 全局共享 BitmapContext：CEP 和 Need 规则跨批次复用叶子 bitmap 缓存
    shared_ctx = bm_eng.BitmapContext(con)

    if args.cep_rules:
        cep_rules = _load_json_file(args.cep_rules)
        cep_result = import_cep_rules(
            con, cep_rules,
            force=args.force, dry_run=args.dry_run, min_user_count=args.min_users,
            ctx=shared_ctx,
        )
        if cep_result["accepted"] and not args.dry_run:
            ontology._sep("自动刷新 user_segments")
            analytics.run_segment_rules(con, cep_result["accepted"])

    if args.need_rules:
        ontology_path = args.ontology or config.ONTOLOGY_PATH
        G = nx.DiGraph()
        if os.path.exists(ontology_path):
            G = ontology.load_ontology(ontology_path)
            print(f"  [图谱] 已加载 {ontology_path}（节点={G.number_of_nodes()}，边={G.number_of_edges()}）")
        else:
            print(f"  ⚠  图谱不存在: {ontology_path}，在空图上操作")

        need_rules = _load_json_file(args.need_rules)
        need_result = import_need_rules(
            con, G, need_rules,
            force=args.force, dry_run=args.dry_run, min_user_count=args.min_users,
            ctx=shared_ctx,
        )
        if need_result["accepted"] and not args.dry_run:
            save_path = args.save_ontology or ontology_path
            ontology.save_ontology(G, save_path)
            print(f"\n  [图谱] 已保存到 {save_path}")

    if not args.dry_run:
        stats = shared_ctx.cache_stats()
        print(f"\n  [Bitmap 全局缓存] 命中={stats['hits']} 未命中={stats['misses']} "
              f"命中率={stats['hits']/(stats['hits']+stats['misses'])*100:.0f}%"
              if (stats['hits']+stats['misses']) > 0 else "")

    ontology._sep("规则导入完成")


if __name__ == "__main__":
    main()
