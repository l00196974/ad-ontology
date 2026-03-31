"""
MarketingNeed 全局单例注册表
============================
提供 NeedSingletonRegistry，统一管理 8 个 MarketingNeed 实例。

设计动机：
  原代码中用 8 个 global 变量（NEED_GREEN_PLATE 等）存储需求单例，
  规则函数直接引用这些全局变量，导致规则模块与 ABox 模块形成隐式耦合。
  重构为注册表后，规则通过 get_need(NeedKey.GREEN_PLATE) 获取实例，
  解耦了规则与 ABox 加载顺序，并支持单测独立构造 ABox 状态。
"""

from ontology_engine.config.enums import NeedKey
from ontology_engine.core.ontology_registry import get_onto


class NeedSingletonRegistry:
    """MarketingNeed 实例注册表（Dict[NeedKey, OWL Individual]）"""

    def __init__(self):
        self._registry: dict = {}

    def register(self, key: NeedKey, instance) -> None:
        """注册一个需求实例"""
        self._registry[key] = instance

    def get(self, key: NeedKey):
        """
        获取需求实例。若未注册则抛出 KeyError（表明 ABox 未正确加载）。
        """
        if key not in self._registry:
            raise KeyError(
                f"NeedKey '{key}' 未注册。请先调用 load_abox() 初始化 ABox。"
            )
        return self._registry[key]

    def all(self) -> dict:
        """返回全部注册的需求实例（{key: instance}）"""
        return dict(self._registry)

    def is_loaded(self) -> bool:
        """检查注册表是否已填充"""
        return len(self._registry) > 0

    def clear(self) -> None:
        """清空注册表（测试用）"""
        self._registry.clear()


# 模块级单例注册表
_REGISTRY = NeedSingletonRegistry()

# 便捷访问函数，规则层统一使用此接口
get_need = _REGISTRY.get


def initialize_need_singletons() -> None:
    """
    在 onto 上下文中预创建所有 MarketingNeed 全局单例实例，并注册到表中。
    必须在 build_tbox() 之后、推理规则执行之前调用。
    """
    onto = get_onto()
    with onto:
        _REGISTRY.register(NeedKey.GREEN_PLATE,     onto.GreenPlateRequired("need_绿牌刚需"))
        _REGISTRY.register(NeedKey.NO_PARKING,      onto.NoParkingLimitNumber("need_无桩且限号"))
        _REGISTRY.register(NeedKey.LICENSE_FREE,    onto.LicenseFree("need_牌照自由"))
        _REGISTRY.register(NeedKey.SIX_SEVEN_SEATS, onto.SixSevenSeatsRequired("need_刚需6至7座"))
        _REGISTRY.register(NeedKey.SINGLE_COMMUTE,  onto.SinglePersonCommute("need_单人代步"))
        _REGISTRY.register(NeedKey.BUDGET_LOCKED,   onto.BudgetLocked("need_预算死锁"))
        _REGISTRY.register(NeedKey.FLEXIBLE_BUDGET, onto.FlexibleBudget("need_弹性预算"))
        _REGISTRY.register(NeedKey.RANGE_ANXIETY,   onto.RangeMileageAnxiety("need_里程焦虑"))
        _REGISTRY.register(NeedKey.LONG_COMMUTE,    onto.LongCommuteUser("need_通勤距离增加"))

    print(f"[ABox] NeedSingletonRegistry 初始化完成，共 {len(_REGISTRY.all())} 个需求实例")
