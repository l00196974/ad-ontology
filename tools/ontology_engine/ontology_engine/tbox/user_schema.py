"""
User TBox 模式定义
==================
定义 User OWL 类及其全部 17 个数据属性（DataProperty）。
每个属性均标注数据映射来源和枚举值范围，作为用户本体的权威文档。
"""

from owlready2 import Thing, DataProperty, FunctionalProperty
from ontology_engine.core.ontology_registry import get_onto


def build_user_schema() -> type:
    """
    在 onto 上下文中定义 User 类及全部数据属性。
    返回 User 类，供其他模块引用。
    """
    onto = get_onto()
    with onto:

        class User(Thing):
            """
            人的本体。
            代表华为广告生态中的真实用户画像。
            TBox 维度覆盖：生理性别与年龄代际、城市政策环境、
            消费力分层、出行行为、营销触达、购车行为漏斗等。
            """
            pass

        # ── 生理性别与年龄代际 ────────────────────────────────────────────────

        class age_range(DataProperty, FunctionalProperty):
            """年龄区间 KEY。枚举：AgeRange。来源：底层基础画像。"""
            domain = [User]; range = [str]

        class gender(DataProperty, FunctionalProperty):
            """生理性别。枚举：Gender。来源：底层基础画像。"""
            domain = [User]; range = [str]

        class generation_group(DataProperty, FunctionalProperty):
            """代际标签。枚举：GenerationGroup。由 age_range 通过映射计算。"""
            domain = [User]; range = [str]

        # ── 常驻城市级别与政策环境 ───────────────────────────────────────────

        class city_tier(DataProperty, FunctionalProperty):
            """城市等级。枚举：CityTier。来源：底层基础画像。"""
            domain = [User]; range = [str]

        class policy_restriction_fuel(DataProperty, FunctionalProperty):
            """燃油车政策。枚举：PolicyFuel。来源：get_car_policy()。"""
            domain = [User]; range = [str]

        class policy_restriction_ev(DataProperty, FunctionalProperty):
            """新能源车政策。枚举：PolicyEV。来源：get_car_policy()。"""
            domain = [User]; range = [str]

        # ── 预估消费力 ────────────────────────────────────────────────────────

        class device_price_tier(DataProperty, FunctionalProperty):
            """华为设备价格分层。枚举：DevicePriceTier。来源：设备价格映射表。"""
            domain = [User]; range = [str]

        # ── 核心用车与出行场景 ───────────────────────────────────────────────

        class travel_activity(DataProperty, FunctionalProperty):
            """基础出行活跃度。枚举：TravelActivity。来源：地图/打车 APP 行为。"""
            domain = [User]; range = [str]

        # ── 资讯获取平台 ──────────────────────────────────────────────────────

        class media_preference(DataProperty, FunctionalProperty):
            """核心触媒偏好。枚举：MediaPreference。来源：各平台搜索/浏览行为占比。"""
            domain = [User]; range = [str]

        # ── 计划购车预算区间 ──────────────────────────────────────────────────

        class interaction_price_band(DataProperty, FunctionalProperty):
            """泛交互预估预算区间（Top5 交互车型反查中位价）。枚举：PriceBand。"""
            domain = [User]; range = [str]

        class inquiry_price_band(DataProperty, FunctionalProperty):
            """显性询价预算区间（查落地价 SPU 反查价格带）。枚举：PriceBand。"""
            domain = [User]; range = [str]

        # ── 底价试探行为 ──────────────────────────────────────────────────────

        class inquiry_frequency(DataProperty, FunctionalProperty):
            """
            询价触发频次（"查落地价"累计次数）。
            整数值：1=单次询价，≥2=多频底价试探。
            """
            domain = [User]; range = [int]

        # ── 销售跟进与沟通 ───────────────────────────────────────────────────

        class sales_contact_count(DataProperty, FunctionalProperty):
            """联系销售次数。来源：垂媒"联系销售"动作计数。"""
            domain = [User]; range = [int]

        class lead_online(DataProperty, FunctionalProperty):
            """线上留资次数。来源：线上渠道留资动作。"""
            domain = [User]; range = [int]

        class lead_offline(DataProperty, FunctionalProperty):
            """线下留资次数。来源：线下渠道留资动作。"""
            domain = [User]; range = [int]

        # ── 门店距离与试驾 ───────────────────────────────────────────────────

        class store_nearby_count(DataProperty, FunctionalProperty):
            """路过门店次数（WIFI 捕获）。"""
            domain = [User]; range = [int]

        class test_drive_status(DataProperty, FunctionalProperty):
            """试驾状态。枚举：TestDriveStatus。来源：底层流转日志试驾节点标签。"""
            domain = [User]; range = [str]

        # ── 订单转化阶段 ──────────────────────────────────────────────────────

        class conversion_stage(DataProperty, FunctionalProperty):
            """当前最高转化阶段（漏斗水位 Max）。枚举：ConversionStage。"""
            domain = [User]; range = [str]

        # ── 通勤行为 ──────────────────────────────────────────────────────────

        class commute_distance_delta(DataProperty, FunctionalProperty):
            """
            通勤距离变化量（单位：km）。
            表示用户近期通勤距离相比历史基线的增加值。
            ≥ 10km 被视为"通勤距离显著增加"，触发 LongCommuteRule。
            来源：地图 APP 通勤轨迹分析。
            """
            domain = [User]; range = [float]

    return onto.User
