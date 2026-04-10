"""
原始数据加载器
==============
负责从用户提供的 txt 文件（画像 + 行为）加载到 DuckDB，
并打印加载摘要和数据概览。
"""
from __future__ import annotations

from neotrace.storage.base import StorageAdapter


class RawDataLoader:

    def __init__(self, storage: StorageAdapter):
        self._storage = storage

    def load(self, profiles_path: str, behaviors_path: str) -> dict:
        """
        加载画像和行为数据，返回摘要。

        Args:
            profiles_path: 用户画像 txt 文件路径
            behaviors_path: 用户行为 txt 文件路径

        Returns:
            {profile_count, behavior_count, conversion_rate, profile_schema, behavior_schema}
        """
        print(f"[DataLoader] 加载画像数据: {profiles_path}")
        profile_count = self._storage.load_raw_profiles(profiles_path)
        print(f"  ✓ 画像加载完成: {profile_count:,} 条")

        print(f"[DataLoader] 加载行为数据: {behaviors_path}")
        behavior_count = self._storage.load_raw_behaviors(behaviors_path)
        print(f"  ✓ 行为加载完成: {behavior_count:,} 条")

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
