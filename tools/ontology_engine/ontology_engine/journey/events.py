"""
事理图谱事件体系
================
定义 35 个购车相关事件（E001-E506），涵盖：
  - 生活事件（E001-E009）：结婚、离婚、生育、怀孕、搬家、新工作等
  - 兴趣事件（E101-E105）：开始关注汽车、频繁浏览、深度浏览、收藏、分享
  - 搜索事件（E201-E207）：搜索品牌/价格/参数/对比/购车指南/贷款/竞品
  - APP使用事件（E301-E307）：安装汽车资讯APP、车贷计算器、对比工具等
  - 位置事件（E401-E404）：到访4S店/车展/交通枢纽/新区域
  - 购车阶段事件（E501-E506）：兴趣萌发→信息收集→方案对比→金融咨询→线下看车→意向确认

每个事件包含时间窗口（短期7天/中期30天/长期90天/超长期180天）和触发条件描述。
"""

from dataclasses import dataclass, field
from enum import Enum


class EventType(str, Enum):
    LIFE        = "生活事件"
    INTEREST    = "兴趣事件"
    SEARCH      = "搜索事件"
    APP_USAGE   = "APP使用事件"
    LOCATION    = "位置事件"
    PURCHASE    = "购车阶段事件"


@dataclass(frozen=True)
class PurchaseEvent:
    """购车事件定义"""
    event_id:          str        # E001, E101, ...
    event_name:        str        # 中文名称
    event_type:        EventType
    time_window_days:  int        # 有效观察窗口（天）
    trigger_condition: str        # 触发条件描述（自然语言）
    signal_strength:   float = 1.0  # 信号强度 0-1，越高越确定性


# ─────────────────────────────────────────────────────────────────────────────
# 生活事件（E001-E009）— 长期窗口，触发购车意图的外部生活变化
# ─────────────────────────────────────────────────────────────────────────────
LIFE_EVENTS: list[PurchaseEvent] = [
    PurchaseEvent("E001", "结婚",         EventType.LIFE, 180, "婚庆相关APP安装或搜索婚庆关键词", 0.58),
    PurchaseEvent("E002", "离婚",         EventType.LIFE, 90,  "离婚相关法律咨询搜索",            0.40),
    PurchaseEvent("E003", "生育",         EventType.LIFE, 365, "母婴APP安装或育儿内容深度浏览",    0.72),
    PurchaseEvent("E004", "怀孕",         EventType.LIFE, 270, "孕期相关APP/搜索行为",            0.65),
    PurchaseEvent("E005", "搬家",         EventType.LIFE, 90,  "搬家公司搜索或新区域POI访问",      0.45),
    PurchaseEvent("E006", "新工作",       EventType.LIFE, 90,  "招聘APP活跃或职场相关搜索",        0.50),
    PurchaseEvent("E007", "通勤距离增加", EventType.LIFE, 30,  "地图通勤路线拉长，平均>1小时",     0.65),
    PurchaseEvent("E008", "车辆出售",     EventType.LIFE, 30,  "二手车平台评估/挂售行为",          0.82),
    PurchaseEvent("E009", "车辆故障",     EventType.LIFE, 7,   "汽车维修搜索或4S店紧急预约",       0.55),
]

# ─────────────────────────────────────────────────────────────────────────────
# 兴趣事件（E101-E105）— 中期窗口，主动关注汽车内容的行为信号
# ─────────────────────────────────────────────────────────────────────────────
INTEREST_EVENTS: list[PurchaseEvent] = [
    PurchaseEvent("E101", "开始关注汽车",   EventType.INTEREST, 30, "首次浏览汽车垂媒或汽车相关内容",     0.60),
    PurchaseEvent("E102", "频繁浏览汽车",   EventType.INTEREST, 30, "7天内汽车内容浏览≥5次",             0.72),
    PurchaseEvent("E103", "深度浏览车型",   EventType.INTEREST, 30, "单车型详情页停留>3分钟或查看配置表", 0.80),
    PurchaseEvent("E104", "收藏/关注车型", EventType.INTEREST, 30, "垂媒收藏或关注特定车型/品牌",        0.75),
    PurchaseEvent("E105", "分享汽车内容",   EventType.INTEREST, 30, "分享汽车测评/车型对比文章",          0.65),
]

# ─────────────────────────────────────────────────────────────────────────────
# 搜索事件（E201-E207）— 短期窗口，主动搜索是强意图信号
# ─────────────────────────────────────────────────────────────────────────────
SEARCH_EVENTS: list[PurchaseEvent] = [
    PurchaseEvent("E201", "搜索品牌",     EventType.SEARCH, 7,  "搜索特定汽车品牌关键词",           0.70),
    PurchaseEvent("E202", "搜索价格",     EventType.SEARCH, 7,  "搜索'XX车多少钱'/'XX车落地价'等",   0.78),
    PurchaseEvent("E203", "搜索参数",     EventType.SEARCH, 7,  "搜索续航/动力/油耗等技术参数",      0.72),
    PurchaseEvent("E204", "搜索对比",     EventType.SEARCH, 7,  "搜索'XX vs XX'或'XX和XX哪个好'",   0.75),
    PurchaseEvent("E205", "搜索购车指南", EventType.SEARCH, 14, "搜索'买车流程''提车注意事项'等",    0.68),
    PurchaseEvent("E206", "搜索贷款",     EventType.SEARCH, 14, "搜索'汽车贷款''首付比例''月供'等", 0.70),
    PurchaseEvent("E207", "搜索竞品",     EventType.SEARCH, 7,  "搜索竞争品牌或同级别车型对比",      0.68),
]

# ─────────────────────────────────────────────────────────────────────────────
# APP 使用事件（E301-E307）— 长期窗口，APP 安装/使用反映持续关注
# ─────────────────────────────────────────────────────────────────────────────
APP_EVENTS: list[PurchaseEvent] = [
    PurchaseEvent("E301", "安装汽车资讯APP", EventType.APP_USAGE, 90, "安装懂车帝/汽车之家/易车等APP",    0.72),
    PurchaseEvent("E302", "安装购车APP",     EventType.APP_USAGE, 90, "安装二手车/购车平台APP",           0.75),
    PurchaseEvent("E303", "使用车贷计算器", EventType.APP_USAGE, 30, "使用车贷计算相关功能",             0.80),
    PurchaseEvent("E304", "使用汽车论坛",   EventType.APP_USAGE, 30, "汽车论坛/社区发帖或深度阅读",      0.65),
    PurchaseEvent("E305", "使用对比工具",   EventType.APP_USAGE, 14, "使用多车型参数对比功能",           0.78),
    PurchaseEvent("E306", "安装育儿APP",    EventType.APP_USAGE, 90, "安装育儿/母婴相关APP（关联家庭扩展）", 0.55),
    PurchaseEvent("E307", "安装健身APP",    EventType.APP_USAGE, 90, "安装运动健身APP（关联生活方式升级）", 0.40),
]

# ─────────────────────────────────────────────────────────────────────────────
# 位置事件（E401-E404）— 短期窗口，物理行为是最强意图信号
# ─────────────────────────────────────────────────────────────────────────────
LOCATION_EVENTS: list[PurchaseEvent] = [
    PurchaseEvent("E401", "到访4S店",   EventType.LOCATION, 7,  "WIFI/GPS捕获到访汽车品牌4S店",    0.88),
    PurchaseEvent("E402", "到访车展",   EventType.LOCATION, 7,  "到访汽车展览会/车展",              0.85),
    PurchaseEvent("E403", "交通枢纽",   EventType.LOCATION, 30, "高频到访地铁/公交枢纽（潜在补能焦虑）", 0.45),
    PurchaseEvent("E404", "探索新区域", EventType.LOCATION, 30, "最近30天出现新的常驻区域",         0.50),
]

# ─────────────────────────────────────────────────────────────────────────────
# 购车阶段事件（E501-E506）— 漏斗标签，对应 conversion_stage
# ─────────────────────────────────────────────────────────────────────────────
PURCHASE_STAGE_EVENTS: list[PurchaseEvent] = [
    PurchaseEvent("E501", "兴趣萌发",   EventType.PURCHASE, 30, "首次汽车相关行为触发",             0.60),
    PurchaseEvent("E502", "信息收集",   EventType.PURCHASE, 30, "多车型浏览+搜索组合行为",          0.70),
    PurchaseEvent("E503", "方案对比",   EventType.PURCHASE, 14, "跨品牌/跨价格带的对比行为",        0.78),
    PurchaseEvent("E504", "金融咨询",   EventType.PURCHASE, 14, "车贷计算+询价行为组合",            0.82),
    PurchaseEvent("E505", "线下看车",   EventType.PURCHASE, 7,  "到访4S店+同期询价行为",            0.90),
    PurchaseEvent("E506", "意向确认",   EventType.PURCHASE, 7,  "联系销售/留资/试驾/小订等动作",    0.95),
]

# 全部事件的平铺列表和 ID 索引
ALL_EVENTS: list[PurchaseEvent] = (
    LIFE_EVENTS + INTEREST_EVENTS + SEARCH_EVENTS +
    APP_EVENTS + LOCATION_EVENTS + PURCHASE_STAGE_EVENTS
)

EVENT_INDEX: dict[str, PurchaseEvent] = {e.event_id: e for e in ALL_EVENTS}
