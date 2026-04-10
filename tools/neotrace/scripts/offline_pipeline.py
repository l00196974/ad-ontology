#!/usr/bin/env python3
"""
NEOTrace 离线 Pipeline 主入口
==============================

完整执行顺序：
  Step 1: 加载原始数据（画像 + 行为 txt）→ DuckDB
  Step 2: 统计数据分布
  Step 3: LLM 挖掘 CEP 行为清洗规则 → 计算 TGI → 保存 draft
  Step 4: [交互] 人工审核 CEP 规则，选择发布/拒绝
  Step 5: 基于已发布 CEP 规则构建本体（TBox + ABox）
  Step 6: 生成 PySpark 打标作业（输出到 output/spark_tagging_job.py）

用法:
  python offline_pipeline.py \\
      --profiles  data/user_profiles.txt \\
      --behaviors data/user_behaviors.txt \\
      [--db       neotrace.duckdb] \\
      [--cep-rules 10] \\
      [--auto-publish] \\
      [--min-tgi 110]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 确保 neotrace 包可导入
sys.path.insert(0, str(Path(__file__).parent.parent))

from neotrace.storage.duckdb_adapter import DuckDBAdapter
from neotrace.ingest.loader import RawDataLoader
from neotrace.mining.stats import DataProfiler
from neotrace.mining.cep_miner import CepMiner
from neotrace.mining.rule_store import RuleStore
from neotrace.ontology.tbox.tbox_builder import build_tbox
from neotrace.ontology.abox.abox_loader import load_abox
from neotrace.spark.generator import SparkGenerator


def parse_args():
    p = argparse.ArgumentParser(description="NEOTrace 离线 Pipeline")
    p.add_argument("--profiles",     required=True,  help="用户数据 txt 文件路径（合并格式含 user_tag+user_events，或双文件模式下的画像文件）")
    p.add_argument("--behaviors",    default=None,   help="行为 txt 文件路径（双文件模式时填写，合并格式可省略）")
    p.add_argument("--db",           default="neotrace.duckdb", help="DuckDB 数据库路径")
    p.add_argument("--cep-rules",    type=int, default=10, help="LLM 生成 CEP 规则数量")
    p.add_argument("--auto-publish", action="store_true",  help="自动发布达标规则，不交互审核")
    p.add_argument("--val-ratio",     type=float, default=0.2, help="验证集比例（默认 0.2，分层抽样保证正负比例一致）")
    p.add_argument("--min-tgi-cep",  type=float, default=100.0, help="CEP 自动发布 TGI 阈值")
    p.add_argument("--output-dir",   default="output", help="输出目录")
    p.add_argument("--media-config", default=None,  help="媒体广告位配置 JSON 文件路径（可选）")
    p.add_argument("--skip-steps",   default="",   help="跳过步骤，逗号分隔，如 1,2")
    return p.parse_args()


def main():
    args = parse_args()
    skip = set(args.skip_steps.split(",")) if args.skip_steps else set()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("  NEOTrace 离线 Pipeline 启动")
    print("=" * 60)

    # 初始化存储
    storage = DuckDBAdapter(db_path=args.db)
    rule_store = RuleStore(storage)

    # ── Step 1: 加载数据 ──────────────────────────────────────────────────────
    if "1" not in skip:
        print("\n[Step 1] 加载原始数据...")
        loader = RawDataLoader(storage)
        summary = loader.load(args.profiles, args.behaviors, val_ratio=args.val_ratio)
        print(f"  全样本留资率: {summary['conversion_rate']:.2%}")
    else:
        print("\n[Step 1] 跳过数据加载")

    # ── Step 2: 数据分布统计 ──────────────────────────────────────────────────
    if "2" not in skip:
        print("\n[Step 2] 统计数据分布...")
        profiler = DataProfiler(storage)
        profile_result = profiler.profile()
        # 保存分布报告
        report_path = output_dir / "data_profile.txt"
        report_path.write_text(profile_result["summary_text"], encoding="utf-8")
        print(f"  分布报告已保存至: {report_path}")
    else:
        print("\n[Step 2] 跳过分布统计")

    # ── Step 3: CEP 规则挖掘 ─────────────────────────────────────────────────
    if "3" not in skip:
        print(f"\n[Step 3] LLM 挖掘 CEP 行为清洗规则 (目标 {args.cep_rules} 条)...")
        cep_miner = CepMiner(storage)
        cep_candidates = cep_miner.mine(n_rules=args.cep_rules)
        print(f"\n  生成 CEP 候选规则: {len(cep_candidates)} 条")
    else:
        print("\n[Step 3] 跳过 CEP 规则挖掘")

    # ── Step 4: CEP 规则审核 ─────────────────────────────────────────────────
    if "4" not in skip:
        print("\n[Step 4] CEP 规则审核...")
        if args.auto_publish:
            n = rule_store.publish_all_cep(min_tgi=args.min_tgi_cep)
            print(f"  自动发布 {n} 条 CEP 规则（TGI ≥ {args.min_tgi_cep}）")
        else:
            _interactive_review(rule_store, rule_type="cep_clean")
    else:
        print("\n[Step 4] 跳过 CEP 规则审核")

    # ── Step 5: 构建本体 ─────────────────────────────────────────────────────
    if "5" not in skip:
        print("\n[Step 5] 构建广告本体（TBox + ABox）...")
        build_tbox()
        load_abox(storage, item_config_path=args.media_config)
        print("  本体构建完成")
    else:
        print("\n[Step 5] 跳过本体构建")

    # ── Step 6: 生成 Spark 作业 ───────────────────────────────────────────────
    if "6" not in skip:
        print("\n[Step 6] 生成 PySpark 打标作业...")
        gen = SparkGenerator(storage)
        spark_path = output_dir / "spark_tagging_job.py"
        gen.save(str(spark_path))
        print(f"  PySpark 作业已保存至: {spark_path}")
    else:
        print("\n[Step 6] 跳过 Spark 作业生成")

    # ── 最终报告 ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  Pipeline 完成，规则汇总:")
    rule_store.print_report()

    storage.close()
    print("\n  输出文件目录:", output_dir.absolute())


def _interactive_review(rule_store: RuleStore, rule_type: str) -> None:
    """交互式规则审核"""
    pending = rule_store.list_pending(rule_type=rule_type)
    if not pending:
        print("  无待审核规则")
        return

    print(f"\n  待审核规则 {len(pending)} 条（类型: {rule_type}）")
    print(f"  {'ID':<10} {'名称':<30} {'TGI':>6} {'覆盖':>8} {'命中':>10}")
    print(f"  {'-'*10} {'-'*30} {'-'*6} {'-'*8} {'-'*10}")
    for r in pending:
        print(f"  {r['rule_id'][:8]:<10} {r.get('name','')[:30]:<30} "
              f"  {r.get('tgi') or 0:>5.1f} "
              f"{r.get('support') or 0:>7.1%} "
              f"{r.get('hit_users') or 0:>10,}")

    print("\n  命令: [rule_id] p=发布 / r=拒绝 / a=全部发布 / q=退出")
    while True:
        cmd = input("  > ").strip().lower()
        if cmd == "q":
            break
        elif cmd == "a":
            for r in pending:
                rule_store.publish(r["rule_id"])
            print(f"  已发布全部 {len(pending)} 条规则")
            break
        elif " " in cmd:
            parts = cmd.split()
            if len(parts) == 2:
                rule_prefix, action = parts
                matched = [r for r in pending if r["rule_id"].startswith(rule_prefix)]
                if matched:
                    rule_id = matched[0]["rule_id"]
                    if action == "p":
                        rule_store.publish(rule_id)
                    elif action == "r":
                        rule_store.reject(rule_id)
                else:
                    print(f"  未找到规则: {rule_prefix}")


if __name__ == "__main__":
    main()
