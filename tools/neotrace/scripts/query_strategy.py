#!/usr/bin/env python3
"""
策略查询
用法:
  python scripts/query_strategy.py --item "东风猛士917" --budget 500000 --db output/my.duckdb

可选参数:
  --media-config data/mengshi_media.json   媒体广告位配置（可选）
  --objective    conversions               优化目标：conversions / reach / clicks
"""
import argparse, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from neotrace.storage.duckdb_adapter import DuckDBAdapter
from neotrace.strategy.engine import StrategyEngine
from neotrace.ontology.tbox.tbox_builder import build_tbox
from neotrace.ontology.abox.abox_loader import load_abox


def main():
    p = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--item",         required=True,           help="车型名称，如 '东风猛士917'")
    p.add_argument("--budget",       required=True, type=float, help="总预算（元），如 500000")
    p.add_argument("--db",           default="neotrace.duckdb", help="DuckDB 数据库路径")
    p.add_argument("--media-config", default=None,            help="媒体广告位配置 JSON（可选）")
    p.add_argument("--objective",    default="conversions",
                   choices=["conversions", "reach", "clicks"], help="优化目标（默认 conversions）")
    args = p.parse_args()

    storage = DuckDBAdapter(db_path=args.db)

    # 构建本体（TBox + ABox）
    build_tbox()
    load_abox(storage, item_config_path=args.media_config)

    engine = StrategyEngine(storage)
    result = engine.query(args.item, budget=args.budget, objective=args.objective)

    # 输出策略摘要
    print("\n" + "=" * 60)
    print("  投放策略")
    print("=" * 60)
    print(f"\n  {result.summary}")

    print(f"\n  目标人群:")
    print(f"    规模:     {result.total_users:,} 人")
    print(f"    意向分:   P90={result.intent_score_p90:.3f}  P50={result.intent_score_p50:.3f}")
    print(f"    参考 TGI: {result.avg_tgi:.0f}")
    if result.inferred_needs:
        print(f"    需求标签: {' / '.join(result.inferred_needs)}")
    if result.matched_rules:
        print(f"    核心规则: {' / '.join(result.matched_rules)}")

    if result.placements:
        print(f"\n  推荐媒体:")
        for pl in result.placements:
            print(f"    · {pl.platform} — {pl.ad_format} ({pl.buying_type})"
                  f"  预算 {pl.budget_allocated/10000:.1f}万"
                  f"  预估触达 {pl.estimated_reach:,}人")

    if result.creatives:
        print(f"\n  推荐素材:")
        for cr in result.creatives:
            print(f"    · [{cr.theme}] {cr.key_message}")

    print(f"\n  效果预估:")
    print(f"    预估触达: {result.estimated_reach:,} 人")
    print(f"    预估转化: {result.estimated_conversions:,} 人")

    storage.close()


if __name__ == "__main__":
    main()
