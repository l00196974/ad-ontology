#!/usr/bin/env python3
"""
CEP 规则挖掘
用法:
  python scripts/mine_rules.py --db output/my.duckdb [--n-rules 5]

可选过滤:
  --min-support 0.01   过滤掉命中人群覆盖率低于此值的规则（默认不过滤）
                       覆盖率 = 命中用户数 / 总用户数，太小的规则圈不到足够人群
"""
import argparse, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from neotrace.storage.duckdb_adapter import DuckDBAdapter
from neotrace.mining.cep_miner import CepMiner
from neotrace.mining.rule_store import RuleStore
from neotrace.mining.stats import DataProfiler


def _stability_tag(train_tgi: float, val_tgi: float, threshold: float = 0.2) -> str:
    """判断规则稳定性：训练集与验证集 TGI 偏差超过阈值则标记为不稳定"""
    if train_tgi <= 0:
        return "⚠ 无法判断"
    deviation = abs(train_tgi - val_tgi) / train_tgi
    if deviation <= threshold:
        return "✓ 稳定"
    return f"⚠ 不稳定 (偏差 {deviation:.0%})"


def main():
    p = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db",               default="neotrace.duckdb", help="DuckDB 数据库路径")
    p.add_argument("--n-rules",          type=int,   default=5,     help="目标有效规则数（循环挖掘直到达标）")
    p.add_argument("--max-rounds",       type=int,   default=3,     help="最大挖掘轮次（默认 3 轮）")
    p.add_argument("--min-support",      type=float, default=0.0,
                   help="过滤命中人群覆盖率低于此值的规则，如 0.01 表示至少覆盖 1%% 用户（默认不过滤）")
    p.add_argument("--stability-thresh", type=float, default=0.2,
                   help="稳定性判断阈值（训练/验证 TGI 偏差比例，默认 0.2）")
    args = p.parse_args()

    storage = DuckDBAdapter(db_path=args.db)
    rule_store = RuleStore(storage)

    # 打印数据分布（供人工参考，同时 CepMiner 内部也会用于 LLM prompt）
    print("\n[mine_rules] 统计数据分布...")
    profile_result = DataProfiler(storage).profile()
    print(profile_result["summary_text"])
    print()

    # 检查是否有验证集数据
    stats = storage.get_split_stats()
    has_val = "val" in stats and stats["val"]["total"] > 0
    if has_val:
        val_total = stats["val"]["total"]
        val_pos_rate = stats["val"]["pos_rate"]
        print(f"[mine_rules] 检测到验证集: {val_total:,} 用户  正样本率 {val_pos_rate:.1%}")
        print(f"  将对每条规则同时在训练集和验证集上计算 TGI（偏差阈值 {args.stability_thresh:.0%}）")
    else:
        print("[mine_rules] 未检测到验证集，仅在全量数据上计算 TGI")
        print("  提示: 使用 load_data.py --val-ratio 0.2 导入时自动划分验证集")

    # 挖掘（循环直到达标或达到最大轮次）
    candidates = CepMiner(storage).mine(n_rules=args.n_rules, max_rounds=args.max_rounds)

    # 如果有验证集，补充计算 val TGI
    if has_val:
        print(f"\n[mine_rules] 在验证集上计算 TGI...")
        for rule in candidates:
            sql_cond = rule.get("sql_condition", "1=1")
            val_result = storage.compute_tgi(sql_cond, split="val")
            rule["val_tgi"] = val_result["tgi"]
            rule["val_support"] = val_result["support"]
            rule["val_hit_users"] = val_result["hit_users"]

    # 按覆盖率过滤（人群规模太小的规则实际圈不到足够用户），过滤掉的直接标记为 rejected
    if args.min_support > 0:
        keep, reject = [], []
        for r in candidates:
            (keep if (r.get("support") or 0) >= args.min_support else reject).append(r)
        if reject:
            for r in reject:
                rule_store.reject(r["rule_id"])
            print(f"\n  已自动废弃 {len(reject)} 条覆盖率 < {args.min_support:.1%} 的规则（人群规模过小，已写入 rejected 供下次挖掘参考）")
        candidates = keep

    if not candidates:
        print("  无可用规则，退出")
        storage.close()
        return

    # 逐条展示，用户选择是否入库
    print("\n" + "=" * 60)
    print("  规则审核 — 逐条确认是否发布入库")
    print("  命令: y=发布  n=跳过  q=退出")
    print("=" * 60)

    published, rejected_count = 0, 0
    for i, rule in enumerate(candidates, 1):
        train_tgi = rule.get("tgi") or 0
        print(f"\n  [{i}/{len(candidates)}] {rule['name']}")
        print(f"    训练集: TGI={train_tgi:.1f}  覆盖={rule.get('support') or 0:.1%}  命中={rule.get('hit_users') or 0:,}人")

        if has_val:
            val_tgi = rule.get("val_tgi") or 0
            stability = _stability_tag(train_tgi, val_tgi, args.stability_thresh)
            print(f"    验证集: TGI={val_tgi:.1f}  覆盖={rule.get('val_support') or 0:.1%}  命中={rule.get('val_hit_users') or 0:,}人  {stability}")

        print(f"    说明: {rule.get('description', '')}")
        print(f"    条件: {rule.get('sql_condition', '')}")

        while True:
            cmd = input("  发布? [y=发布/n=废弃/q=退出] > ").strip().lower()
            if cmd in ("y", "n", "q"):
                break

        if cmd == "q":
            print("  已退出")
            break
        elif cmd == "y":
            rule_store.publish(rule["rule_id"])
            published += 1
        else:
            rule_store.reject(rule["rule_id"])
            rejected_count += 1

    print(f"\n  完成: 发布 {published} 条，废弃 {rejected_count} 条（废弃规则将在下次挖掘时反馈给 LLM）")

    # 展示当前已发布规则汇总
    all_published = rule_store.list_published(rule_type="cep_clean")
    print(f"\n  当前已发布 CEP 规则共 {len(all_published)} 条:")
    for r in all_published:
        print(f"    · {r['name']}  TGI={r.get('tgi') or 0:.1f}  覆盖={r.get('support') or 0:.1%}")

    storage.close()


if __name__ == "__main__":
    main()
