"""
规则 2：空间/座位刚需推导
==========================
根据用户代际标签 + 交互车型的车身类型/尺寸级别，推导座位需求。

业务逻辑：
  中坚家庭/银发群体 + 交互含 MPV 或大型 SUV → 刚需 6-7 座
  年轻新贵/新锐青年 + 交互含轿车/小型 SUV    → 单人代步
"""

from ontology_engine.rules.base_rule import BaseRule
from ontology_engine.config.enums import NeedKey, GenerationGroup, BodyType, CarSizeLevel


# 家庭购车代际标签
FAMILY_GENERATIONS = {GenerationGroup.CORE_FAMILY, GenerationGroup.SILVER_HAIR}

# 年轻购车代际标签
YOUNG_GENERATIONS = {GenerationGroup.YOUNG_ELITE, GenerationGroup.RISING_YOUTH}

# 大型家庭车的车身+尺寸组合
LARGE_FAMILY_BODY_SIZE = {
    (BodyType.MPV, None),          # 任何尺寸的 MPV
    (BodyType.SUV, CarSizeLevel.MID_LARGE),
    (BodyType.SUV, CarSizeLevel.LARGE),
}

# 单人通勤的小型车判断
SMALL_COMMUTE_BODIES = {BodyType.SEDAN}
SMALL_SUV_SIZES      = {CarSizeLevel.MICRO, CarSizeLevel.MINI, CarSizeLevel.COMPACT}


class SpaceNeedRule(BaseRule):
    """空间/座位刚需推导规则"""
    rule_id    = "space_need"
    depends_on = []

    def evaluate(self, user) -> list[NeedKey]:
        generation = user.generation_group or ""
        triggered  = []

        body_size_pairs = [
            (car.body_type or "", car.car_size_level or "")
            for car in user.has_interacted_with
        ]

        # 子规则 2a：家庭代际 + 大型家庭车 → 刚需 6-7 座
        if generation in FAMILY_GENERATIONS:
            has_large = any(
                bt == BodyType.MPV
                or (bt == BodyType.SUV and sl in {CarSizeLevel.MID_LARGE, CarSizeLevel.LARGE})
                for bt, sl in body_size_pairs
            )
            if has_large:
                triggered.append(NeedKey.SIX_SEVEN_SEATS)
                self._log(user.name, "刚需6至7座", True,
                          f"代际={generation}，交互含MPV/大型SUV")

        # 子规则 2b：年轻代际 + 小型车/轿车 → 单人代步
        if generation in YOUNG_GENERATIONS:
            has_small = any(
                bt == BodyType.SEDAN
                or (bt == BodyType.SUV and sl in SMALL_SUV_SIZES)
                for bt, sl in body_size_pairs
            )
            if has_small:
                triggered.append(NeedKey.SINGLE_COMMUTE)
                self._log(user.name, "单人代步", True,
                          f"代际={generation}，交互含轿车/小型SUV")

        return triggered
