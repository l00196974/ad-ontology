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
    p.add_argument("--item",           required=True,             help="车型名称，如 '东风猛士917'")
    p.add_argument("--budget",         required=True, type=float, help="总预算（元），如 500000")
    p.add_argument("--audience-size",  type=int, default=0,
                   help="目标投放人群数量（不填则由预算自动推算）")
    p.add_argument("--db",             default="neotrace.duckdb", help="DuckDB 数据库路径")
    p.add_argument("--media-config",   default=None,              help="媒体广告位配置 JSON（可选）")
    p.add_argument("--objective",      default="conversions",
                   choices=["conversions", "reach", "clicks"],    help="优化目标（默认 conversions）")
    args = p.parse_args()

    storage = DuckDBAdapter(db_path=args.db)

    # 构建本体（TBox + ABox）
    build_tbox()
    load_abox(storage, item_config_path=args.media_config)

    engine = StrategyEngine(storage)
    result = engine.query(
        args.item,
        budget=args.budget,
        target_audience_size=args.audience_size,
        objective=args.objective,
    )

    # 输出策略摘要
    print("\n" + "=" * 60)
    print("  投放策略")
    print("=" * 60)
    print(f"\n  {result.summary}")

    print(f"\n  目标人群:")
    print(f"    规模:     {result.total_users:,} 人")
    print(f"    意向分:   P90={result.intent_score_p90:.4f}  P50={result.intent_score_p50:.4f}")
    print(f"    参考 TGI: {result.avg_tgi:.0f}")
    if result.inferred_needs:
        print(f"    需求标签: {' / '.join(result.inferred_needs)}")

    # 按主导需求分组展示
    if result.need_groups:
        print(f"\n  需求分组投放策略 ({len(result.need_groups)} 组):")
        for g in result.need_groups:
            pct = g.user_count * 100 // result.total_users if result.total_users else 0
            print(f"\n  ┌─ [{g.need_label}]  权重={g.need_weight:.0%}  "
                  f"用户 {g.user_count:,}人({pct}%)  "
                  f"预算 {g.budget_allocated/10000:.1f}万  "
                  f"平均意向分 {g.avg_score:.4f}")
            if g.placements:
                for pl in g.placements:
                    print(f"  │  媒体: {pl.ad_format} ({pl.buying_type})"
                          f"  预算 {pl.budget_allocated/10000:.1f}万"
                          f"  预估触达 {pl.estimated_reach:,}人")
            if g.creatives:
                for cr in g.creatives:
                    print(f"  │  素材: [{cr.theme}] {cr.key_message[:40]}")
            print(f"  └{'─'*55}")

    print(f"\n  效果预估:")
    print(f"    预估触达: {result.estimated_reach:,} 人")
    print(f"    预估转化: {result.estimated_conversions:,} 人")

    storage.close()


if __name__ == "__main__":
    main()
