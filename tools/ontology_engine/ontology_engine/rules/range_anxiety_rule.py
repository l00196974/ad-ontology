"""
规则 4：里程/补能焦虑推导
==========================
识别对纯电续航存在顾虑的用户。

前置依赖：license_plate_urgency（必须先执行）
  → 互斥逻辑：已推导出"绿牌刚需"的用户，其规避纯电的行为
    另有解释（城市政策强制），不应再叠加"里程焦虑"标签。

触发条件：
  高频出行活跃 + 交互偏好燃油/增程（无纯电交互）+ 非绿牌刚需城市
  → 用户主动规避纯电续航风险
"""

from ontology_engine.rules.base_rule import BaseRule
from ontology_engine.config.enums import NeedKey, TravelActivity, PowerType
from ontology_engine.abox.need_singletons import get_need


HIGH_ACTIVITY_LEVELS = {TravelActivity.HIGH_MAP_RIDE, TravelActivity.HIGH_RENT}


class RangeAnxietyRule(BaseRule):
    """里程/补能焦虑推导规则（依赖牌照刚需规则先行执行）"""
    rule_id    = "range_mileage_anxiety"
    depends_on = ["license_plate_urgency"]   # 拓扑排序保证此规则在其后执行

    def evaluate(self, user) -> list[NeedKey]:
        travel       = user.travel_activity or ""
        interacted   = user.has_interacted_with
        power_types  = {car.power_type for car in interacted if car.power_type}
        triggered    = []

        has_fuel_pref   = PowerType.FUEL in power_types or PowerType.EREV in power_types
        no_ev_pref      = PowerType.PURE_EV not in power_types

        # 互斥检查：已推导出绿牌刚需的用户，其动力偏好另有解释
        already_green_plate = get_need(NeedKey.GREEN_PLATE) in user.has_inferred_need

        if (
            travel in HIGH_ACTIVITY_LEVELS
            and has_fuel_pref
            and no_ev_pref
            and not already_green_plate
        ):
            triggered.append(NeedKey.RANGE_ANXIETY)
            self._log(user.name, "严重里程焦虑", True,
                      f"出行活跃={travel}，动力偏好={power_types}，非绿牌城市")

        return triggered
