"""
典型购车链路定义
================
定义 5 条典型购车链路（Purchasing Journeys），
每条链路是一个有序的事件节点序列，代表一类用户的购车行为模式。

数据来源：汽车行业广告投放事理图谱文档（内部研究结果）。
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class JourneyNode:
    """链路中的一个节点（事件 + 到达此节点的条件概率）"""
    event_id:    str
    probability: float   # P(到达此节点 | 已到达前一节点)


@dataclass(frozen=True)
class PurchaseJourney:
    """典型购车链路定义"""
    journey_id:     str
    journey_name:   str
    nodes:          tuple[JourneyNode, ...]   # 有序事件节点
    target_persona: str                       # 目标人群描述
    budget_range:   str                       # 预算区间
    recommended_cars: tuple[str, ...]         # 推荐车型（问界优先）
    overall_prob:   float                     # 链路整体转化概率（实测值）


PURCHASE_JOURNEYS: list[PurchaseJourney] = [

    PurchaseJourney(
        journey_id   = "J001",
        journey_name = "家庭扩展型",
        nodes        = (
            JourneyNode("E003", 1.0),   # 生育/新增孩子（触发点）
            JourneyNode("E101", 0.72),  # 开始关注汽车
            JourneyNode("E102", 0.55),  # 频繁浏览
            JourneyNode("E103", 0.48),  # 深度浏览车型
            JourneyNode("E206", 0.50),  # 搜索贷款方案
            JourneyNode("E303", 0.45),  # 使用车贷计算器
            JourneyNode("E401", 0.45),  # 到访4S店
            JourneyNode("E506", 0.55),  # 意向确认
        ),
        target_persona   = "已婚有孩、大空间需求、重视安全性与舒适性",
        budget_range     = "20-35万",
        recommended_cars = ("问界M7", "理想L7", "蔚来ES6"),
        overall_prob     = 0.72,
    ),

    PurchaseJourney(
        journey_id   = "J002",
        journey_name = "通勤不便型",
        nodes        = (
            JourneyNode("E007", 1.0),   # 通勤距离增加（触发点）
            JourneyNode("E101", 0.65),
            JourneyNode("E201", 0.70),  # 搜索品牌
            JourneyNode("E202", 0.70),  # 搜索价格
            JourneyNode("E203", 0.65),  # 搜索参数（续航/油耗）
            JourneyNode("E204", 0.60),  # 搜索对比
            JourneyNode("E206", 0.65),  # 搜索贷款
            JourneyNode("E303", 0.45),  # 车贷计算器
        ),
        target_persona   = "通勤时间>1小时、关注出行成本、倾向新能源",
        budget_range     = "15-25万",
        recommended_cars = ("问界M5", "深蓝S7", "比亚迪汉"),
        overall_prob     = 0.65,
    ),

    PurchaseJourney(
        journey_id   = "J003",
        journey_name = "车辆置换型",
        nodes        = (
            JourneyNode("E008", 1.0),   # 车辆出售/评估（触发点，最强信号 82%）
            JourneyNode("E101", 0.82),
            JourneyNode("E201", 0.70),
            JourneyNode("E202", 0.65),
            JourneyNode("E204", 0.60),  # 搜索对比
            JourneyNode("E207", 0.65),  # 搜索竞品
            JourneyNode("E401", 0.52),  # 到访4S店
        ),
        target_persona   = "现有车>5年/故障频发，关注品牌升级与保值率",
        budget_range     = "25-40万",
        recommended_cars = ("问界M7", "理想L8", "蔚来ES8"),
        overall_prob     = 0.82,
    ),

    PurchaseJourney(
        journey_id   = "J004",
        journey_name = "新婚购车型",
        nodes        = (
            JourneyNode("E001", 1.0),   # 结婚（触发点）
            JourneyNode("E101", 0.58),
            JourneyNode("E201", 0.70),
            JourneyNode("E202", 0.65),
            JourneyNode("E206", 0.50),  # 搜索贷款
            JourneyNode("E303", 0.45),  # 车贷计算器
            JourneyNode("E401", 0.45),  # 到访4S店
        ),
        target_persona   = "新婚夫妻、关注舒适性与外观、接受新能源",
        budget_range     = "15-30万",
        recommended_cars = ("问界M5", "深蓝S7", "比亚迪海豹"),
        overall_prob     = 0.58,
    ),

    PurchaseJourney(
        journey_id   = "J005",
        journey_name = "竞品转化型",
        nodes        = (
            JourneyNode("E102", 1.0),   # 频繁浏览（已在看车）
            JourneyNode("E201", 0.70),
            JourneyNode("E207", 0.75),  # 搜索竞品（核心信号）
            JourneyNode("E204", 0.50),  # 搜索对比
            JourneyNode("E303", 0.65),  # 车贷计算器
        ),
        target_persona   = "竞品（理想/蔚来/小鹏）意向用户，处于横向比较阶段",
        budget_range     = "25-35万",
        recommended_cars = ("问界M7", "问界M9"),
        overall_prob     = 0.68,
    ),
]

JOURNEY_INDEX: dict[str, PurchaseJourney] = {j.journey_id: j for j in PURCHASE_JOURNEYS}
