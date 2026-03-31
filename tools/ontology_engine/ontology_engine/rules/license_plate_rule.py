"""
规则 1：牌照刚需推导
====================
根据城市限行/限牌政策 + 用户交互车型的动力类型，推导牌照刚需类别。

SWRL 等价伪代码：
  User(?u) ∧ policy_restriction_fuel(?u, "燃油车限牌限行")
  ∧ has_interacted_with(?u, ?car) ∧ power_type(?car, "纯电动")
  → has_inferred_need(?u, need_绿牌刚需)

  User(?u) ∧ policy_restriction_fuel(?u, "燃油车限牌限行")
  ∧ has_interacted_with(?u, ?car)
  ∧ power_type(?car, "插电式混合动力" OR "增程式")  [且无纯电交互]
  → has_inferred_need(?u, need_无桩且限号)

  User(?u) ∧ policy_restriction_fuel(?u, "燃油车无限制")
  → has_inferred_need(?u, need_牌照自由)
"""

from ontology_engine.rules.base_rule import BaseRule
from ontology_engine.config.enums import NeedKey, PolicyFuel, PowerType


class LicensePlateRule(BaseRule):
    """
    牌照刚需推导规则。
    强规则（有明确外部政策约束），无前置依赖，优先执行。
    """
    rule_id    = "license_plate_urgency"
    depends_on = []

    def evaluate(self, user) -> list[NeedKey]:
        fuel_policy   = user.policy_restriction_fuel or PolicyFuel.UNKNOWN
        interacted    = user.has_interacted_with

        # 统计交互车型的动力类型集合
        power_types = {car.power_type for car in interacted if car.power_type}

        is_restricted = fuel_policy in (
            PolicyFuel.RESTRICTED_BOTH,
            PolicyFuel.RESTRICTED_PLATE,
            PolicyFuel.RESTRICTED_ROAD,
        )

        triggered = []

        if is_restricted:
            # 子规则 1a：限号城市 + 交互含纯电 → 绿牌刚需
            if PowerType.PURE_EV in power_types:
                triggered.append(NeedKey.GREEN_PLATE)
                self._log(user.name, "绿牌刚需/有桩无畏", True,
                          f"城市政策={fuel_policy}，交互含纯电车型")

            # 子规则 1b：限号城市 + 插混/增程（但无纯电） → 无桩且限号
            has_plugin = (PowerType.PHEV in power_types or PowerType.EREV in power_types)
            if has_plugin and PowerType.PURE_EV not in power_types:
                triggered.append(NeedKey.NO_PARKING)
                self._log(user.name, "无桩且限号", True,
                          f"城市政策={fuel_policy}，交互含插混/增程但无纯电")

        elif fuel_policy == PolicyFuel.NO_RESTRICTION:
            # 子规则 1c：无限制城市 → 牌照自由
            triggered.append(NeedKey.LICENSE_FREE)
            self._log(user.name, "牌照自由", True, f"城市政策={fuel_policy}")

        return triggered
