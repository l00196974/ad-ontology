"""
存储抽象层基类
"""
from abc import ABC, abstractmethod
from typing import Any

try:
    import pyarrow as pa
    _PA_AVAILABLE = True
except ImportError:
    pa = None  # type: ignore
    _PA_AVAILABLE = False


class StorageAdapter(ABC):

    # ── 原始数据操作 ──────────────────────────────────────────────────────────

    @abstractmethod
    def load_raw_profiles(self, path: str) -> int:
        """从文件加载用户画像数据，返回加载行数"""
        ...

    @abstractmethod
    def load_raw_behaviors(self, path: str) -> int:
        """从文件加载用户行为数据，返回加载行数"""
        ...

    # ── 数据分布统计 ──────────────────────────────────────────────────────────

    @abstractmethod
    def get_profile_schema(self) -> dict[str, str]:
        """返回画像字段名 → 类型映射"""
        ...

    @abstractmethod
    def get_behavior_schema(self) -> dict[str, str]:
        """返回行为字段名 → 类型映射"""
        ...

    @abstractmethod
    def get_field_distribution(self, table: str, field: str) -> list[dict]:
        """返回字段值分布：[{value, count, pct}]"""
        ...

    @abstractmethod
    def get_conversion_rate(self) -> float:
        """返回全样本留资率（转化锚点）"""
        ...

    # ── 语义事件流操作 ────────────────────────────────────────────────────────

    @abstractmethod
    def insert_semantic_events(self, events: list[dict]) -> None:
        """写入语义事件（CEP 清洗产出）"""
        ...

    @abstractmethod
    def rebuild_feature_wide_table(self) -> None:
        """从语义事件流 PIVOT 重建宽表视图"""
        ...

    @abstractmethod
    def get_feature_table(self) -> "pa.Table":
        """返回用户特征宽表（Arrow Table，供 DuckDB 快速查询）"""
        ...

    # ── 规则存储 ──────────────────────────────────────────────────────────────

    @abstractmethod
    def save_rule(self, rule: dict) -> str:
        """保存规则（draft 状态），返回 rule_id"""
        ...

    @abstractmethod
    def get_rules(self, status: str) -> list[dict]:
        """查询规则列表，status: draft | validated | published | rejected"""
        ...

    @abstractmethod
    def update_rule_status(self, rule_id: str, status: str, metrics: dict | None = None) -> None:
        """更新规则状态及验证指标"""
        ...

    # ── TGI 计算 ──────────────────────────────────────────────────────────────

    @abstractmethod
    def compute_tgi(self, sql_condition: str) -> dict:
        """
        计算满足条件的用户群的 TGI（留资浓度比）。
        TGI = (命中用户留资率 / 全样本留资率) × 100
        返回: {hit_users, hit_conversion_rate, global_conversion_rate, tgi, support}
        """
        ...
