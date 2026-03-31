"""
枚举常量模块
============
集中定义所有 OWL 属性域的枚举值，消灭魔法字符串散落各文件的问题。
规则、ABox、查询层均通过 Enum 成员引用，变更只需改此一处。
"""

from enum import Enum


# ── 人的本体枚举 ─────────────────────────────────────────────────────────────

class AgeRange(str, Enum):
    """年龄区间（原始 KEY）"""
    UNDER_18  = "18岁以下"
    AGE_18_23 = "18-23岁"
    AGE_24_34 = "24-34岁"
    AGE_35_44 = "35-44岁"
    AGE_45_54 = "45-54岁"
    OVER_55   = "55岁以上"


class Gender(str, Enum):
    """生理性别"""
    MALE    = "男"
    FEMALE  = "女"
    UNKNOWN = "未知"


class GenerationGroup(str, Enum):
    """代际标签（由 age_range 映射）"""
    SILVER_HAIR     = "银发群体"    # 55岁以上
    CORE_FAMILY     = "中坚家庭"    # 35-54岁
    YOUNG_ELITE     = "年轻新贵"    # 24-34岁
    RISING_YOUTH    = "新锐青年"    # 18-23岁
    FUTURE_OWNER    = "未来车主"    # 18岁以下

    @classmethod
    def from_age_range(cls, age_range: str) -> "GenerationGroup":
        """根据年龄区间 KEY 返回代际标签"""
        mapping = {
            AgeRange.UNDER_18:  cls.FUTURE_OWNER,
            AgeRange.AGE_18_23: cls.RISING_YOUTH,
            AgeRange.AGE_24_34: cls.YOUNG_ELITE,
            AgeRange.AGE_35_44: cls.CORE_FAMILY,
            AgeRange.AGE_45_54: cls.CORE_FAMILY,
            AgeRange.OVER_55:   cls.SILVER_HAIR,
        }
        return mapping.get(age_range, cls.FUTURE_OWNER)


class CityTier(str, Enum):
    """城市等级"""
    TIER_1        = "一线城市"
    NEW_TIER_1    = "新一线城市"
    TIER_2        = "二线城市"
    TIER_3        = "三线城市"
    TIER_4_PLUS   = "四五线及以下城市"


class PolicyFuel(str, Enum):
    """燃油车政策限制"""
    RESTRICTED_BOTH  = "燃油车限牌限行"
    RESTRICTED_PLATE = "燃油车仅限牌"
    RESTRICTED_ROAD  = "燃油车仅限行"
    NO_RESTRICTION   = "燃油车无限制"
    UNKNOWN          = "未知"


class PolicyEV(str, Enum):
    """新能源车政策限制"""
    RESTRICTED_PLATE = "新能源车仅限牌"
    NO_RESTRICTION   = "新能源车无限制"
    UNKNOWN          = "未知"


class DevicePriceTier(str, Enum):
    """华为设备价格分层（反映消费力）"""
    ENTRY_LEVEL  = "入门级设备"    # 1000以内
    LOW_MID      = "中低端设备"    # 1000~2000
    MID          = "中端设备"      # 2000~3000
    MID_HIGH     = "中高端设备"    # 3000~5000
    HIGH_END     = "高端设备"      # 5000~8000
    FLAGSHIP     = "旗舰设备"      # 8000以上


class TravelActivity(str, Enum):
    """基础出行活跃度"""
    HIGH_MAP_RIDE   = "高频地图/打车用户"
    BASE_MAP_RIDE   = "基础地图/打车用户"
    LOW_MAP_RIDE    = "低活跃地图/打车用户"
    NON_MAP_RIDE    = "非租车地图/打车用户"
    HIGH_RENT       = "高频租车用户"
    BASE_RENT       = "基础租车用户"
    LOW_RENT        = "低活跃租车用户"
    NON_RENT        = "非租车用户"


class MediaPreference(str, Enum):
    """核心触媒偏好"""
    ENTERTAINMENT   = "泛娱乐种草媒体偏好型"
    NEWS            = "泛资讯媒体偏好型"
    AUTO_VERTICAL   = "三车垂媒偏好型"
    BALANCED        = "多端均分型"


class PriceBand(str, Enum):
    """价格带（人车共用，保持枚举值绝对一致）"""
    UNDER_10W   = "10万以下"
    W10_20      = "10-20万"
    W20_30      = "20-30万"
    W30_50      = "30-50万"
    W50_100     = "50-100万"
    OVER_100W   = "100万以上"
    NO_EXPLICIT = "无显性询价"
    NO_CLEAR    = "无明确车型"


class ConversionStage(str, Enum):
    """订单所处客观阶段（漏斗水位 Max）"""
    NO_LEAD     = "暂未留资"
    LEAD        = "留资"
    TEST_DRIVE  = "试驾"
    SOFT_ORDER  = "小订"
    HARD_ORDER  = "大定"


class TestDriveStatus(str, Enum):
    """试驾状态"""
    DONE     = "已试驾"
    NOT_DONE = "未试驾"


# ── 车的本体枚举 ─────────────────────────────────────────────────────────────

class BodyType(str, Enum):
    """车身结构分类"""
    SEDAN   = "轿车"
    SUV     = "SUV"
    MPV     = "MPV"
    SPORTS  = "跑车"
    PICKUP  = "皮卡"
    MINI_VAN = "微面"
    LIGHT_BUS = "轻客"


class CarSizeLevel(str, Enum):
    """通用尺寸级别"""
    MICRO       = "微型(A00)"
    MINI        = "小型(A0)"
    COMPACT     = "紧凑型(A)"
    MID         = "中型(B)"
    MID_LARGE   = "中大型(C)"
    LARGE       = "大型(D)"


class PowerType(str, Enum):
    """驱动能源类型"""
    PURE_EV = "纯电动"
    PHEV    = "插电式混合动力"
    EREV    = "增程式"
    FUEL    = "传统燃油"
    HEV     = "油电混合"
    OTHER   = "其它"


class BrandCamp(str, Enum):
    """品牌阵营"""
    OWN_BRAND      = "本品"
    CORE_RIVAL     = "核心竞品阵营"
    LUXURY_TRAD    = "传统豪华品牌"
    JOINT_VENTURE  = "合资品牌"
    DOMESTIC       = "自主品牌"
    NEW_FORCE      = "造车新势力"


# ── 需求本体枚举 key ──────────────────────────────────────────────────────────

class NeedKey(str, Enum):
    """MarketingNeed 单例注册表的 key，规则层通过此 key 引用需求实例"""
    GREEN_PLATE      = "绿牌刚需"
    NO_PARKING       = "无桩且限号"
    LICENSE_FREE     = "牌照自由"
    SIX_SEVEN_SEATS  = "刚需6至7座"
    SINGLE_COMMUTE   = "单人代步"
    BUDGET_LOCKED    = "预算死锁"
    FLEXIBLE_BUDGET  = "弹性预算"
    RANGE_ANXIETY    = "里程焦虑"
    LONG_COMMUTE     = "通勤距离增加"
