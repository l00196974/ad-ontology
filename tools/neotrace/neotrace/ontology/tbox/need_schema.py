"""
NEED TBox 模式（从已发布规则动态生成）
======================================
核心设计：NEED 类型由挖掘验证后的规则决定，不再硬编码。
固定的顶层分类（FunctionalNeed/FinancialNeed/...）保留，
具体子类在 build 时从已发布规则动态创建。
"""
from __future__ import annotations

from owlready2 import Thing, DataProperty, FunctionalProperty, AllDisjoint

from neotrace.ontology.registry import get_onto


# 顶层 NEED 分类（固定，不随规则变化）
TOP_LEVEL_CATEGORIES = {
    "牌照刚需":   "LicensePlateUrgency",
    "空间刚需":   "SpaceNeed",
    "预算敏感":   "BudgetSensitivity",
    "里程焦虑":   "RangeMileageAnxiety",
    "通勤需求":   "CommuteNeed",
}


def build_need_schema(published_need_rules: list[dict] | None = None) -> type:
    """
    构建 NEED TBox。

    Args:
        published_need_rules: 已发布的 need_segment 规则列表，
                              每条规则对应一个具体 NEED 子类。
                              为 None 时使用内置默认类。
    Returns:
        MarketingNeed 基类
    """
    onto = get_onto()
    with onto:

        class MarketingNeed(Thing):
            """广告营销需求本体基类"""
            need_label: str = ""
            category: str = ""
            segment_id: str = ""       # 对应 Spark 打标 key
            avg_tgi: float = 0.0       # 来自验证层

        # 顶层分类
        class LicensePlateUrgency(MarketingNeed):
            category = "牌照刚需"
        class SpaceNeed(MarketingNeed):
            category = "空间刚需"
        class BudgetSensitivity(MarketingNeed):
            category = "预算敏感"
        class RangeMileageAnxiety(MarketingNeed):
            category = "里程焦虑"
        class CommuteNeed(MarketingNeed):
            category = "通勤需求"

        AllDisjoint([
            LicensePlateUrgency, SpaceNeed, BudgetSensitivity,
            RangeMileageAnxiety, CommuteNeed,
        ])

        # 从已发布规则动态创建子类
        if published_need_rules:
            _parent_map = {
                "LicensePlateUrgency": LicensePlateUrgency,
                "SpaceNeed":           SpaceNeed,
                "BudgetSensitivity":   BudgetSensitivity,
                "RangeMileageAnxiety": RangeMileageAnxiety,
                "CommuteNeed":         CommuteNeed,
            }
            for rule in published_need_rules:
                need_label = rule.get("need_label", "")
                parent_cls = _parent_map.get(need_label, MarketingNeed)
                cls_name = _sanitize_class_name(rule.get("name", need_label))
                if not hasattr(onto, cls_name):
                    new_cls = type(cls_name, (parent_cls,), {
                        "need_label": rule.get("name", ""),
                        "category":   parent_cls.category,
                        "segment_id": rule.get("rule_id", ""),
                        "avg_tgi":    float(rule.get("tgi") or 0),
                    })
                    # 注册到 onto
                    new_cls.namespace = onto

    return onto.MarketingNeed


def _sanitize_class_name(name: str) -> str:
    """将中文/空格名称转换为合法 Python 类名"""
    import re
    # 保留字母数字下划线，其余替换为下划线
    s = re.sub(r"[^\w]", "_", name)
    if s[0].isdigit():
        s = "N_" + s
    return s
