"""
原始数据加载器
==============
负责从用户提供的 txt 文件加载到 DuckDB，并打印加载摘要。

支持两种模式：
  1. 单文件模式（合并格式）：一个 txt 文件，每行包含 user_tag + user_events
  2. 双文件模式（独立格式）：画像文件 + 行为文件分开传入
"""
from __future__ import annotations

from neotrace.storage.base import StorageAdapter


class RawDataLoader:

    def __init__(self, storage: StorageAdapter):
        self._storage = storage

    def load(
        self,
        input_path: str,
        behaviors_path: str | None = None,
        val_ratio: float = 0.0,
    ) -> dict:
        """
        加载数据，返回摘要。

        Args:
            input_path:     合并格式 txt（含 user_tag + user_events），
                            或双文件模式下的画像文件路径
            behaviors_path: 双文件模式下的行为文件路径（可选）
            val_ratio:      验证集比例（0.0 表示全部训练集，分层抽样保证正负比例一致）

        Returns:
            {profile_count, behavior_count, conversion_rate, ...}
        """
        if behaviors_path:
            # 双文件模式
            print(f"[DataLoader] 加载画像数据: {input_path}")
            profile_count = self._storage.load_raw_profiles(input_path, val_ratio=val_ratio)
            print(f"  ✓ 画像加载完成: {profile_count:,} 条")

            print(f"[DataLoader] 加载行为数据: {behaviors_path}")
            behavior_count = self._storage.load_raw_behaviors(behaviors_path)
            print(f"  ✓ 行为加载完成: {behavior_count:,} 条")
        else:
            # 单文件模式（合并格式，同一文件同时写入画像和行为）
            print(f"[DataLoader] 加载合并数据: {input_path}")
            profile_count = self._storage.load_raw_profiles(input_path, val_ratio=val_ratio)
            behavior_count = self._storage.load_raw_behaviors(input_path)
            print(f"  ✓ 加载完成: {profile_count:,} 用户, {behavior_count:,} 条行为")

        conversion_rate = self._storage.get_conversion_rate()
        profile_schema = self._storage.get_profile_schema()
        behavior_schema = self._storage.get_behavior_schema()

        print(f"\n[DataLoader] 数据概览:")
        print(f"  用户数:       {profile_count:,}")
        print(f"  行为记录数:   {behavior_count:,}")
        print(f"  全样本留资率: {conversion_rate:.2%}")
        print(f"  画像字段数:   {len(profile_schema)}")
        print(f"  行为字段数:   {len(behavior_schema)}")

        return {
            "profile_count": profile_count,
            "behavior_count": behavior_count,
            "conversion_rate": conversion_rate,
            "profile_schema": profile_schema,
            "behavior_schema": behavior_schema,
        }
