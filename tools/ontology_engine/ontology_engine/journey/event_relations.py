"""
事件关系体系
============
定义事件之间的因果关系（R001-R015）和顺承关系（S001-S012）。
每条关系包含条件概率，用于购车链路匹配时的路径概率传播。
"""

from dataclasses import dataclass
from enum import Enum


class RelationType(str, Enum):
    CAUSATION   = "因果关系"   # A 的发生是 B 发生的原因
    SEQUENTIAL  = "顺承关系"   # A 之后通常顺序发生 B


@dataclass(frozen=True)
class EventRelation:
    """事件关系定义"""
    relation_id:   str          # R001 / S001
    from_event_id: str          # 前因事件
    to_event_id:   str          # 后果/后续事件
    relation_type: RelationType
    probability:   float        # 条件概率 P(to | from)
    confidence:    float = 0.8  # 规则置信度
    decay_days:    int   = 30   # 有效期（超过此天数后概率衰减）


# ─────────────────────────────────────────────────────────────────────────────
# 因果关系（R001-R015）
# 生活事件 → 汽车关注触发
# ─────────────────────────────────────────────────────────────────────────────
CAUSAL_RELATIONS: list[EventRelation] = [
    EventRelation("R001", "E003", "E101", RelationType.CAUSATION, 0.72, decay_days=180),  # 生育→关注
    EventRelation("R002", "E001", "E101", RelationType.CAUSATION, 0.58, decay_days=180),  # 结婚→关注
    EventRelation("R003", "E007", "E101", RelationType.CAUSATION, 0.65, decay_days=30),   # 通勤增加→关注
    EventRelation("R004", "E008", "E101", RelationType.CAUSATION, 0.82, decay_days=30),   # 车辆出售→关注（最强）
    EventRelation("R005", "E009", "E101", RelationType.CAUSATION, 0.55, decay_days=7),    # 车辆故障→关注
    EventRelation("R006", "E005", "E101", RelationType.CAUSATION, 0.45, decay_days=90),   # 搬家→关注
    EventRelation("R007", "E004", "E003", RelationType.CAUSATION, 0.80, decay_days=270),  # 怀孕→生育
    EventRelation("R008", "E101", "E102", RelationType.CAUSATION, 0.60, decay_days=30),   # 关注→频繁浏览
    EventRelation("R009", "E102", "E103", RelationType.CAUSATION, 0.55, decay_days=30),   # 频繁→深度
    EventRelation("R010", "E201", "E202", RelationType.CAUSATION, 0.75, decay_days=7),    # 搜品牌→搜价格
    EventRelation("R011", "E202", "E206", RelationType.CAUSATION, 0.60, decay_days=14),   # 搜价格→搜贷款
    EventRelation("R012", "E305", "E401", RelationType.CAUSATION, 0.40, decay_days=14),   # 对比工具→到访4S店
    EventRelation("R013", "E401", "E506", RelationType.CAUSATION, 0.55, decay_days=7),    # 到访4S→意向确认
    EventRelation("R014", "E102", "E207", RelationType.CAUSATION, 0.70, decay_days=30),   # 频繁浏览→搜竞品
    EventRelation("R015", "E206", "E303", RelationType.CAUSATION, 0.65, decay_days=14),   # 搜贷款→用车贷计算器
]

# ─────────────────────────────────────────────────────────────────────────────
# 顺承关系（S001-S012）
# 行为序列中的自然后续步骤
# ─────────────────────────────────────────────────────────────────────────────
SEQUENTIAL_RELATIONS: list[EventRelation] = [
    EventRelation("S001", "E101", "E102", RelationType.SEQUENTIAL, 0.55, decay_days=30),  # 关注→频繁浏览
    EventRelation("S002", "E102", "E103", RelationType.SEQUENTIAL, 0.48, decay_days=30),  # 频繁→深度
    EventRelation("S003", "E103", "E104", RelationType.SEQUENTIAL, 0.45, decay_days=14),  # 深度→收藏
    EventRelation("S004", "E201", "E202", RelationType.SEQUENTIAL, 0.70, decay_days=7),   # 搜品牌→搜价格
    EventRelation("S005", "E202", "E203", RelationType.SEQUENTIAL, 0.65, decay_days=7),   # 搜价格→搜参数
    EventRelation("S006", "E203", "E204", RelationType.SEQUENTIAL, 0.60, decay_days=7),   # 搜参数→搜对比
    EventRelation("S007", "E204", "E207", RelationType.SEQUENTIAL, 0.65, decay_days=7),   # 搜对比→搜竞品
    EventRelation("S008", "E305", "E401", RelationType.SEQUENTIAL, 0.40, decay_days=14),  # 对比→到访4S
    EventRelation("S009", "E303", "E401", RelationType.SEQUENTIAL, 0.45, decay_days=14),  # 车贷计算→到访4S
    EventRelation("S010", "E401", "E506", RelationType.SEQUENTIAL, 0.55, decay_days=7),   # 到访4S→意向确认
    EventRelation("S011", "E501", "E502", RelationType.SEQUENTIAL, 0.65, decay_days=30),  # 兴趣→信息收集
    EventRelation("S012", "E502", "E503", RelationType.SEQUENTIAL, 0.58, decay_days=14),  # 信息→方案对比
]

ALL_RELATIONS: list[EventRelation] = CAUSAL_RELATIONS + SEQUENTIAL_RELATIONS
