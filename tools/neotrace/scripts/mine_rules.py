#!/usr/bin/env python3
"""
CEP 规则挖掘
用法:
  python scripts/mine_rules.py --db output/my.duckdb [--n-rules 5] [--min-tgi 100]
"""
import argparse, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from neotrace.storage.duckdb_adapter import DuckDBAdapter
from neotrace.mining.cep_miner import CepMiner
from neotrace.mining.rule_store import RuleStore


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--db",       default="neotrace.duckdb", help="DuckDB 数据库路径")
    p.add_argument("--n-rules",  type=int, default=5,     help="LLM 生成规则数量")
    p.add_argument("--min-tgi",  type=float, default=0,   help="自动过滤 TGI 低于此值的规则（不展示）")
    args = p.parse_args()

    storage = DuckDBAdapter(db_path=args.db)
    rule_store = RuleStore(storage)

    # 挖掘
    candidates = CepMiner(storage).mine(n_rules=args.n_rules)

    # 过滤掉 TGI 太低的
    if args.min_tgi > 0:
        before = len(candidates)
        candidates = [r for r in candidates if (r.get("tgi") or 0) >= args.min_tgi]
        print(f"\n  过滤后剩余 {len(candidates)} 条（过滤掉 {before - len(candidates)} 条 TGI < {args.min_tgi}）")

    if not candidates:
        print("  无可用规则，退出")
        storage.close()
        return

    # 逐条展示，用户选择是否入库
    print("\n" + "=" * 60)
    print("  规则审核 — 逐条确认是否发布入库")
    print("  命令: y=发布  n=跳过  q=退出")
    print("=" * 60)

    published, skipped = 0, 0
    for i, rule in enumerate(candidates, 1):
        print(f"\n  [{i}/{len(candidates)}] {rule['name']}")
        print(f"    TGI={rule.get('tgi') or 0:.1f}  "
              f"覆盖={rule.get('support') or 0:.1%}  "
              f"命中={rule.get('hit_users') or 0:,}人")
        print(f"    说明: {rule.get('description', '')}")
        print(f"    条件: {rule.get('sql_condition', '')}")

        while True:
            cmd = input("  发布? [y/n/q] > ").strip().lower()
            if cmd in ("y", "n", "q"):
                break

        if cmd == "q":
            print("  已退出")
            break
        elif cmd == "y":
            rule_store.publish(rule["rule_id"])
            published += 1
        else:
            skipped += 1

    print(f"\n  完成: 发布 {published} 条，跳过 {skipped} 条")

    # 展示当前已发布规则汇总
    all_published = rule_store.list_published(rule_type="cep_clean")
    print(f"\n  当前已发布 CEP 规则共 {len(all_published)} 条:")
    for r in all_published:
        print(f"    · {r['name']}  TGI={r.get('tgi') or 0:.1f}  覆盖={r.get('support') or 0:.1%}")

    storage.close()


if __name__ == "__main__":
    main()
