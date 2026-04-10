#!/usr/bin/env python3
"""
数据导入
用法:
  python scripts/load_data.py --input data/users.txt --db output/my.duckdb [--val-ratio 0.2]
"""
import argparse, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from neotrace.storage.duckdb_adapter import DuckDBAdapter
from neotrace.ingest.loader import RawDataLoader
from neotrace.mining.stats import DataProfiler


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input",      required=True,  help="合并格式 txt（含 user_tag + user_events）")
    p.add_argument("--db",         default="neotrace.duckdb", help="DuckDB 数据库路径")
    p.add_argument("--val-ratio",  type=float, default=0.2,
                   help="验证集比例（默认 0.2，即 80%%训练/20%%验证，分层抽样保证正负比例一致）")
    p.add_argument("--output-dir", default="output", help="报告输出目录")
    args = p.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    storage = DuckDBAdapter(db_path=args.db)
    loader = RawDataLoader(storage)
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
