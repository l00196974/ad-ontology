#!/usr/bin/env python3
"""
benchmark_bitmap.py — 对比 Python set vs Bitmap 两种执行引擎的性能
===================================================================

用法：
  cd tools/ontology_engine && python scripts/benchmark_bitmap.py --db path/to/data.db

输出：
  - 两种引擎执行相同规则集的耗时对比
  - 内存占用估算
  - 结果一致性验证
"""

import argparse
import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))

import rule_expr as rx
import bitmap_engine as bm_eng


def _make_test_rules() -> list[str]:
    """生成测试规则列表（不依赖具体数据，用真实语法但尽量通用）"""
    return [
        # 简单 exists
        "event.Action_Browse_Car_Detail_Freq.exists",
        # count
        "event.Action_Browse_Car_Detail_Freq.count >= 2",
        # AND 组合
        "event.Action_Browse_Car_Detail_Freq.exists AND event.Action_Compare_Car_Models.exists",
        # OR 组合
        "event.Action_Browse_Car_Detail_Freq.exists OR event.Action_Browse_Car_News_Gen.exists",
        # NOT
        "NOT event.Action_Browse_Car_News_Gen.exists",
        # 嵌套 AND/OR
        "(event.Action_Browse_Car_Detail_Freq.count >= 3 OR event.Action_Compare_Car_Models.exists) "
        "AND event.Action_Book_Car_Test_Drive.exists",
        # 复杂 Need 规则
        "event.Action_Browse_Car_Detail_Freq.count >= 3 AND event.Action_Compare_Car_Models.exists "
        "AND event.Action_Book_Car_Test_Drive.exists",
    ]


def run_set_engine(con: sqlite3.Connection, rules: list[str]) -> tuple[list[set], float]:
    """原版 Python set 引擎"""
    t0 = time.perf_counter()
    results = []
    for expr in rules:
        try:
            s = rx.eval_expr(expr, con)
            results.append(s)
        except Exception as e:
            results.append(set())
            print(f"  [set] 规则失败: {e}")
    elapsed = time.perf_counter() - t0
    return results, elapsed


def run_bitmap_engine(con: sqlite3.Connection, rules: list[str]) -> tuple[list[int], float]:
    """新版 Bitmap 引擎（共享 BitmapContext）"""
    ctx = bm_eng.BitmapContext(con)
    t0  = time.perf_counter()
    results = []
    for expr in rules:
        try:
            b = ctx.eval_expr(expr)
            results.append(b)
        except Exception as e:
            results.append(0)
            print(f"  [bm] 规则失败: {e}")
    elapsed = time.perf_counter() - t0
    return results, elapsed, ctx


def check_consistency(
    set_results: list[set],
    bm_results: list[int],
    ctx: bm_eng.BitmapContext,
    rules: list[str],
):
    """验证两种引擎结果完全一致"""
    ok = True
    for i, (s, bm) in enumerate(zip(set_results, bm_results)):
        bm_set = ctx.to_user_set(bm)
        if s != bm_set:
            print(f"  ❌ 规则 {i} 结果不一致！")
            print(f"     set 引擎: {len(s)} 人")
            print(f"     bm  引擎: {len(bm_set)} 人")
            print(f"     仅 set 有: {list(s - bm_set)[:5]}")
            print(f"     仅 bm  有: {list(bm_set - s)[:5]}")
            print(f"     规则: {rules[i]}")
            ok = False
    if ok:
        print("  ✅ 所有规则结果一致")
    return ok


def estimate_memory(user_count: int, result_set: set) -> dict:
    """估算两种方式的内存占用"""
    # set：每个 user_id 字符串约 50 字节 + set 开销约 30%
    set_bytes = len(result_set) * 50 * 1.3 if result_set else 0
    # bitmap：user_count bits = user_count / 8 字节
    bm_bytes = user_count / 8
    return {
        "set_kb":    set_bytes / 1024,
        "bitmap_kb": bm_bytes / 1024,
        "ratio":     set_bytes / bm_bytes if bm_bytes > 0 else 0,
    }


def main():
    parser = argparse.ArgumentParser(description="Bitmap vs Set 引擎性能基准测试")
    parser.add_argument("--db", default="data/ontology.db", help="SQLite 数据库路径")
    parser.add_argument("--repeat", type=int, default=5, help="重复执行次数（取最小值）")
    args = parser.parse_args()

    db_path = os.path.join(os.path.dirname(__file__), "..", args.db) if not os.path.isabs(args.db) else args.db
    if not os.path.exists(db_path):
        print(f"❌ 数据库不存在: {db_path}")
        print("  请先运行 poc_dual_spiral.py 生成数据库，或用 --db 指定路径")
        sys.exit(1)

    con = sqlite3.connect(db_path)

    # 用户总数
    try:
        n_users = con.execute("SELECT COUNT(*) FROM user_profile").fetchone()[0]
        n_events = con.execute("SELECT COUNT(*) FROM user_derived_events").fetchone()[0]
    except Exception as e:
        print(f"❌ 读取数据库失败: {e}")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  数据库: {db_path}")
    print(f"  用户总数: {n_users:,}")
    print(f"  衍生事件行数: {n_events:,}")
    print(f"  重复次数: {args.repeat}")
    print(f"{'='*60}\n")

    rules = _make_test_rules()
    print(f"测试规则数: {len(rules)}\n")

    # ── 内存估算 ────────────────────────────────────────────────────────────
    mem = estimate_memory(n_users, set())
    print(f"内存估算（{n_users:,} 用户，全集 bitmap）：")
    print(f"  Python set（50B/uid）  约 {n_users * 50 / 1024:.0f} KB")
    print(f"  Bitmap int（1bit/uid） 约 {mem['bitmap_kb']:.1f} KB")
    print(f"  压缩比: ~{n_users * 50 * 8 / n_users:.0f}x\n")

    # ── 首轮一致性校验 ────────────────────────────────────────────────────
    print("--- 一致性验证 ---")
    set_res, _ = run_set_engine(con, rules)
    bm_res, _, bm_ctx = run_bitmap_engine(con, rules)
    check_consistency(set_res, bm_res, bm_ctx, rules)

    print(f"\n--- 性能基准（重复 {args.repeat} 次取最短耗时）---")
    print(f"{'规则':<55} {'set(ms)':>8} {'bm(ms)':>8} {'加速比':>7}")
    print("-" * 85)

    for i, expr in enumerate(rules):
        # set 引擎
        set_times = []
        for _ in range(args.repeat):
            t0 = time.perf_counter()
            try:
                rx.eval_expr(expr, con)
            except Exception:
                pass
            set_times.append((time.perf_counter() - t0) * 1000)
        min_set = min(set_times)

        # bitmap 引擎（每次创建新 Context 确保公平，不含初始化时间的话共享 Context 更快）
        bm_times = []
        ctx_init = bm_eng.BitmapContext(con)  # 初始化一次
        for _ in range(args.repeat):
            ctx_init.clear_cache()  # 清除缓存保证公平
            t0 = time.perf_counter()
            try:
                ctx_init.eval_expr(expr)
            except Exception:
                pass
            bm_times.append((time.perf_counter() - t0) * 1000)
        min_bm = min(bm_times)

        speedup = min_set / min_bm if min_bm > 0 else float("inf")
        short_expr = expr[:52] + "..." if len(expr) > 55 else expr
        print(f"  {short_expr:<53} {min_set:>8.2f} {min_bm:>8.2f} {speedup:>6.1f}x")

    # ── 批量规则组合性能（模拟 30 条规则场景）────────────────────────────
    print(f"\n--- 批量规则测试（30条规则，set vs bitmap+共享缓存）---")
    rules_x5 = (rules * 5)[:30]

    # set 引擎
    t0 = time.perf_counter()
    for expr in rules_x5:
        try:
            rx.eval_expr(expr, con)
        except Exception:
            pass
    set_total = (time.perf_counter() - t0) * 1000

    # bitmap 引擎（共享 Context，相同子条件只查一次 SQL）
    ctx_shared = bm_eng.BitmapContext(con)
    t0 = time.perf_counter()
    for expr in rules_x5:
        try:
            ctx_shared.eval_expr(expr)
        except Exception:
            pass
    bm_total = (time.perf_counter() - t0) * 1000

    stats = ctx_shared.cache_stats()
    print(f"  set 引擎（30条）  : {set_total:.1f} ms")
    print(f"  bitmap 引擎（30条）: {bm_total:.1f} ms  加速 {set_total/bm_total:.1f}x")
    print(f"  缓存命中率: {stats['hits']}/{stats['hits']+stats['misses']} = "
          f"{stats['hits']/(stats['hits']+stats['misses'])*100:.0f}%")

    con.close()
    print(f"\n{'='*60}")


if __name__ == "__main__":
    main()
