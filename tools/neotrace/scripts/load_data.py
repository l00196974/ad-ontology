#!/usr/bin/env python3
"""
数据导入
用法（单文件模式）:
  python scripts/load_data.py --input data/users.txt --db output/my.duckdb

用法（正负样本双文件模式）:
  python scripts/load_data.py --pos data/positive.txt --neg data/negative.txt --db output/my.duckdb

可选参数:
  --val-ratio 0.2   验证集比例（默认 0.2，分层抽样保证正负比例一致）
"""
import argparse, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from neotrace.storage.duckdb_adapter import DuckDBAdapter
from neotrace.ingest.loader import RawDataLoader
from neotrace.mining.stats import DataProfiler


def main():
    p = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter)
    # 单文件模式
    p.add_argument("--input",      default=None, help="合并格式 txt（含 user_tag + user_events）")
    # 正负样本双文件模式
    p.add_argument("--pos",        default=None, help="正样本 txt 文件（转化用户，自动打 is_converted=1）")
    p.add_argument("--neg",        default=None, help="负样本 txt 文件（未转化用户，自动打 is_converted=0）")
    # 公共参数
    p.add_argument("--db",         default="neotrace.duckdb", help="DuckDB 数据库路径")
    p.add_argument("--val-ratio",  type=float, default=0.2,
                   help="验证集比例（默认 0.2，即 80%%训练/20%%验证，分层抽样保证正负比例一致）")
    p.add_argument("--overwrite",  action="store_true",
                   help="导入前清空 raw_profiles 和 raw_behaviors，避免重复导入时行为数据翻倍")
    p.add_argument("--output-dir", default="output", help="报告输出目录")
    args = p.parse_args()

    # 参数校验
    if args.pos and args.neg:
        mode = "pos_neg"
    elif args.input:
        mode = "single"
    else:
        p.error("请指定 --input（单文件模式）或同时指定 --pos 和 --neg（双文件模式）")
        return

    if mode == "pos_neg" and args.input:
        p.error("--input 与 --pos/--neg 不能同时使用")
        return

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    storage = DuckDBAdapter(db_path=args.db)

    if args.overwrite:
        storage.truncate_raw_data()
        print("  已清空原始数据表，开始重新导入...")

    loader = RawDataLoader(storage)

    if mode == "pos_neg":
        loader.load_pos_neg(args.pos, args.neg, val_ratio=args.val_ratio)
    else:
        loader.load(args.input, val_ratio=args.val_ratio)

    # 展示分组统计
    stats = storage.get_split_stats()
    print("\n  数据集划分:")
    for split, s in stats.items():
        label = "训练集" if split == "train" else "验证集"
        print(f"    {label} ({split}): {s['total']:,} 用户  "
              f"正样本 {s['pos']:,} ({s['pos_rate']:.1%})")

    # 保存数据分布报告
    profile_result = DataProfiler(storage).profile()
    report_path = output_dir / "data_profile.txt"
    report_path.write_text(profile_result["summary_text"], encoding="utf-8")
    print(f"\n  分布报告已保存: {report_path}")

    storage.close()


if __name__ == "__main__":
    main()
