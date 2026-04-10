"""
数据分布统计器
==============
基于原始数据统计各字段分布，为 LLM 生成 CEP 规则提供数据依据。
"""
from __future__ import annotations

from neotrace.storage.base import StorageAdapter


class DataProfiler:

    def __init__(self, storage: StorageAdapter):
        self._storage = storage

    def profile(self, top_fields: int = 20) -> dict:
        """
        对画像和行为数据做全量分布统计。

        Returns:
            {
              conversion_rate: float,
              profile_fields: {field: [{value, count, pct}]},
              behavior_fields: {field: [{value, count, pct}]},
              summary_text: str   # 供 LLM prompt 使用的文本摘要
            }
        """
        conversion_rate = self._storage.get_conversion_rate()
        profile_schema = self._storage.get_profile_schema()
        behavior_schema = self._storage.get_behavior_schema()

        profile_dists: dict[str, list] = {}
        for field in list(profile_schema.keys())[:top_fields]:
            profile_dists[field] = self._storage.get_field_distribution("profiles", field)

        behavior_dists: dict[str, list] = {}
        for field in list(behavior_schema.keys())[:top_fields]:
            behavior_dists[field] = self._storage.get_field_distribution("behaviors", field)

        summary = self._build_summary_text(
            conversion_rate, profile_dists, behavior_dists
        )

        return {
            "conversion_rate": conversion_rate,
            "profile_fields": profile_dists,
            "behavior_fields": behavior_dists,
            "summary_text": summary,
        }

    def _build_summary_text(
        self,
        cvr: float,
        profile_dists: dict,
        behavior_dists: dict,
    ) -> str:
        """生成供 LLM 使用的分布摘要文本"""
        lines = [
            f"全样本留资率（转化基准）: {cvr:.2%}",
            "",
            "=== 用户画像字段分布（Top值） ===",
        ]
        for field, dist in profile_dists.items():
            top3 = dist[:3]
            vals = ", ".join(f"{d['value']}({d['pct']}%)" for d in top3)
            lines.append(f"  {field}: {vals}")

        lines += ["", "=== 用户行为字段分布（Top值） ==="]
        for field, dist in behavior_dists.items():
            top3 = dist[:3]
            vals = ", ".join(f"{d['value']}({d['pct']}%)" for d in top3)
            lines.append(f"  {field}: {vals}")

        return "\n".join(lines)
