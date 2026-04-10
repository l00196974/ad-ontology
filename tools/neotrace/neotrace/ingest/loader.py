"""
原始数据加载器
==============
负责从用户提供的 txt 文件加载到 DuckDB，并打印加载摘要。

支持三种模式：
  1. 单文件模式（合并格式）：一个 txt 文件，每行包含 user_tag + user_events，
     is_converted 从字段或 user_events 中的留资事件自动推断
  2. 双标签文件模式：正样本文件 + 负样本文件分开传入，
     加载时自动给正样本文件打 is_converted=1，负样本文件打 is_converted=0
  3. 画像+行为双文件模式：画像文件 + 行为文件分开传入
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
        单文件或画像+行为双文件模式。

        Args:
            input_path:     合并格式 txt（含 user_tag + user_events），
                            或双文件模式下的画像文件路径
            behaviors_path: 双文件模式下的行为文件路径（可选）
            val_ratio:      验证集比例（0.0 表示全部训练集，分层抽样保证正负比例一致）
        """
        if behaviors_path:
            print(f"[DataLoader] 加载画像数据: {input_path}")
            profile_count = self._storage.load_raw_profiles(input_path, val_ratio=val_ratio)
            print(f"  ✓ 画像加载完成: {profile_count:,} 条")

            print(f"[DataLoader] 加载行为数据: {behaviors_path}")
            behavior_count = self._storage.load_raw_behaviors(behaviors_path)
            print(f"  ✓ 行为加载完成: {behavior_count:,} 条")
        else:
            print(f"[DataLoader] 加载合并数据: {input_path}")
            profile_count = self._storage.load_raw_profiles(input_path, val_ratio=val_ratio)
            behavior_count = self._storage.load_raw_behaviors(input_path)
            print(f"  ✓ 加载完成: {profile_count:,} 用户, {behavior_count:,} 条行为")

        return self._summary(profile_count, behavior_count)

    def load_pos_neg(
        self,
        pos_path: str,
        neg_path: str,
        val_ratio: float = 0.0,
    ) -> dict:
        """
        正负样本双文件模式：两个文件不含 is_converted 字段，
        由文件身份决定——pos_path 全部打 is_converted=1，neg_path 全部打 is_converted=0。
        行为数据从两个文件各自展开 user_events。

        Args:
            pos_path:  正样本 txt 文件（转化用户）
            neg_path:  负样本 txt 文件（未转化用户）
            val_ratio: 验证集比例（分层抽样，正负各按比例划分）
        """
        print(f"[DataLoader] 加载正样本: {pos_path}")
        pos_count = self._storage.load_raw_profiles(
            pos_path, val_ratio=val_ratio, force_converted=1
        )
        pos_beh = self._storage.load_raw_behaviors(pos_path)
        print(f"  ✓ 正样本: {pos_count:,} 用户, {pos_beh:,} 条行为")

        print(f"[DataLoader] 加载负样本: {neg_path}")
        neg_count = self._storage.load_raw_profiles(
            neg_path, val_ratio=val_ratio, force_converted=0
        )
        neg_beh = self._storage.load_raw_behaviors(neg_path)
        print(f"  ✓ 负样本: {neg_count:,} 用户, {neg_beh:,} 条行为")

        profile_count = pos_count + neg_count
        behavior_count = pos_beh + neg_beh
        return self._summary(profile_count, behavior_count)

    def _summary(self, profile_count: int, behavior_count: int) -> dict:
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
