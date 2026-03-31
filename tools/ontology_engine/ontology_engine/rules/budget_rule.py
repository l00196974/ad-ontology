"""
规则 3：预算敏感度推导
======================
综合推导用户的预算态度（死锁 or 弹性）。

子规则 3a — 预算死锁：
  询价与交互价格区间一致 + 设备偏低端 + 询价频次 ≥ 2
  → 价格是第一决策因子

子规则 3b — 弹性预算：
  交互跨越 ≥ 2 个不同价格带 + 设备高端/旗舰
  → 消费力充裕，产品价值优先
"""

from ontology_engine.rules.base_rule import BaseRule
from ontology_engine.config.enums import NeedKey, DevicePriceTier, PriceBand


LOW_END_DEVICES  = {DevicePriceTier.ENTRY_LEVEL, DevicePriceTier.LOW_MID, DevicePriceTier.MID}
HIGH_END_DEVICES = {DevicePriceTier.HIGH_END, DevicePriceTier.FLAGSHIP}

PRICE_BAND_EXCLUDED = {PriceBand.NO_EXPLICIT, PriceBand.NO_CLEAR}


class BudgetRule(BaseRule):
    """预算敏感度推导规则"""
    rule_id    = "budget_sensitivity"
    depends_on = []

    def evaluate(self, user) -> list[NeedKey]:
        device_tier      = user.device_price_tier or ""
        inquiry_band     = user.inquiry_price_band or ""
        interaction_band = user.interaction_price_band or ""
        inquiry_freq     = user.inquiry_frequency or 0
        triggered        = []

        # 收集交互车型的价格带集合
        interacted_price_bands = {
            car.car_price_band
            for car in user.has_interacted_with
            if car.car_price_band
        }

        # 子规则 3a：预算死锁
        if (
            inquiry_band == interaction_band
            and inquiry_band not in PRICE_BAND_EXCLUDED
            and device_tier in LOW_END_DEVICES
            and inquiry_freq >= 2
        ):
            triggered.append(NeedKey.BUDGET_LOCKED)
            self._log(user.name, "预算死锁", True,
                      f"询价带={inquiry_band}，设备={device_tier}，询价频次={inquiry_freq}")

        # 子规则 3b：弹性预算（跨 ≥ 2 价格带 + 高端设备）
        if len(interacted_price_bands) >= 2 and device_tier in HIGH_END_DEVICES:
            triggered.append(NeedKey.FLEXIBLE_BUDGET)
            self._log(user.name, "弹性预算", True,
                      f"交互价格带={interacted_price_bands}，设备={device_tier}")

        return triggered
