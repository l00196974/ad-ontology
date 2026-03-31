"""
推理规则抽象基类
================
定义 BaseRule 协议，所有业务规则必须继承此类。

设计意图：
  - rule_id：规则的唯一标识，用于注册表 key 和日志
  - depends_on：依赖的前置规则 ID 列表，由 RuleRegistry 拓扑排序保证执行顺序
  - evaluate()：规则核心逻辑，返回触发的 NeedKey 列表
  - _log()：统一触发日志，子类无需重复实现
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from ontology_engine.config.enums import NeedKey

if TYPE_CHECKING:
    from ontology_engine.core.graphdb_client import GraphDBClient


class BaseRule(ABC):
    """推理规则抽象基类"""

    rule_id: str = ""
    """规则唯一标识（子类必须覆盖）"""

    depends_on: list[str] = []
    """
    依赖的前置规则 ID 列表。
    声明依赖后，RuleRegistry 通过拓扑排序保证前置规则先于当前规则执行。
    示例：RangeAnxietyRule.depends_on = ["license_plate_urgency"]
    """

    affected_properties: list[str] = []
    """
    本规则读取的用户 DataProperty 名称列表（可选声明）。
    供 RuleUpdater.re_infer_affected() 缩小需要重推理的用户范围：
      - 若声明了此字段，只对"含有这些属性值的用户"重推（精准模式）
      - 若未声明（空列表），则对所有用户重推（保守模式）

    示例（LicensePlateRule）：
      affected_properties = ["policy_restriction_fuel", "has_interacted_with"]
    """

    def __init__(self):
        self._trigger_log: list[dict] = []

    @abstractmethod
    def evaluate(self, user) -> list[NeedKey]:
        """
        对一个 User 实例执行规则推导。

        参数：
            user: Owlready2 的 User 个体实例（已加载全部 DataProperty）

        返回：
            触发的 NeedKey 列表（空列表表示规则条件未满足，未触发）

        实现要求：
          - 只读用户属性，不直接修改 user.has_inferred_need
          - 由 Reasoner 负责将返回的 NeedKey 转换为 OWL 实例并写入 ABox
          - 可通过 self._log() 记录触发细节
        """
        ...

    def _log(
        self,
        user_name: str,
        need_label: str,
        triggered: bool,
        reason: str = "",
    ) -> None:
        """
        记录规则触发日志并打印。
        子类在 evaluate() 中调用此方法，无需自行实现打印逻辑。
        """
        status = "✅ 触发" if triggered else "⬜ 未触发"
        entry = {
            "rule":    self.rule_id,
            "user":    user_name,
            "need":    need_label if triggered else "-",
            "status":  status,
            "reason":  reason,
        }
        self._trigger_log.append(entry)
        if triggered:
            print(f"  [{status}] 规则「{self.rule_id}」→ 用户「{user_name}」"
                  f"推导出需求「{need_label}」")
            if reason:
                print(f"           原因：{reason}")

    @property
    def log(self) -> list[dict]:
        """返回本规则的触发日志"""
        return list(self._trigger_log)

    def evaluate_sparql(
        self,
        client: "GraphDBClient",
        user_iri: str,
    ) -> list[str]:
        """
        【GraphDB 模式】对一个 User IRI 执行规则推导。

        参数：
            client:   GraphDBClient 实例
            user_iri: 用户个体的完整 IRI（不含尖括号）

        返回：
            触发的 need IRI 列表（完整 IRI 字符串）

        默认实现：抛出 NotImplementedError。
        子规则可选择性覆盖，提供 SPARQL 优化版本；
        若未覆盖，Reasoner 会回退到 evaluate()（内存模式读属性后判断）。
        """
        raise NotImplementedError(
            f"规则 '{self.rule_id}' 尚未实现 evaluate_sparql()，"
            "GraphDB 模式下将回退到内存模式读属性"
        )
