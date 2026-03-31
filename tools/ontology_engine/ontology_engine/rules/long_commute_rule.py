"""
规则 5：通勤距离增加推导
========================
当用户的通勤距离变化量（commute_distance_delta）≥ 10km 时，
推导出"通勤距离增加用户"标签。

业务含义：
  通勤距离显著拉长（如搬家、换工作）意味着用户对续航、补能便利性的
  需求大幅上升，是推荐纯电/增程产品的强信号。

SWRL 等价伪代码：
  User(?u) ∧ commute_distance_delta(?u, ?d) ∧ greaterThanOrEqual(?d, 10.0)
  → has_inferred_need(?u, need_通勤距离增加)
"""

from ontology_engine.rules.base_rule import BaseRule
from ontology_engine.config.enums import NeedKey


class LongCommuteRule(BaseRule):
    """通勤距离增加推导规则"""

    rule_id    = "long_commute"
    depends_on = []
    affected_properties = ["commute_distance_delta"]

    THRESHOLD_KM: float = 10.0
    """通勤距离增加判定阈值（km）"""

    def evaluate(self, user) -> list[NeedKey]:
        delta = user.commute_distance_delta
        if delta is None:
            return []

        try:
            delta = float(delta)
        except (TypeError, ValueError):
            return []

        if delta >= self.THRESHOLD_KM:
            self._log(
                user.name,
                "通勤距离增加用户",
                True,
                f"通勤距离增加 {delta:.1f}km ≥ {self.THRESHOLD_KM}km",
            )
            return [NeedKey.LONG_COMMUTE]

        return []
