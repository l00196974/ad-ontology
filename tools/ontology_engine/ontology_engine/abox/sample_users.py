"""
示例用户实例工厂
================
提供工厂函数创建示例 User 实例。
每个工厂函数独立封装一个用户的全部属性设置，
便于未来替换为从数据库/API 动态加载真实用户画像。
"""

from ontology_engine.core.ontology_registry import get_onto
from ontology_engine.config.enums import (
    AgeRange, Gender, GenerationGroup, CityTier,
    PolicyFuel, PolicyEV, DevicePriceTier, TravelActivity,
    PriceBand, ConversionStage, TestDriveStatus,
)


def create_zhangsan():
    """
    张三：北京限号城市，中坚家庭，看过比亚迪汉（纯电）和丰田汉兰达（燃油）。
    预期推理结果：绿牌刚需 + 刚需6至7座 + 预算死锁。
    """
    onto = get_onto()
    with onto:
        user = onto.User("张三")
        user.age_range                = AgeRange.AGE_35_44.value
        user.gender                   = Gender.MALE.value
        user.generation_group         = GenerationGroup.CORE_FAMILY.value
        user.city_tier                = CityTier.TIER_1.value
        user.policy_restriction_fuel  = PolicyFuel.RESTRICTED_BOTH.value   # 北京：限牌+限行
        user.policy_restriction_ev    = PolicyEV.RESTRICTED_PLATE.value
        user.device_price_tier        = DevicePriceTier.MID.value           # 2000~3000 档
        user.travel_activity          = TravelActivity.HIGH_MAP_RIDE.value
        user.inquiry_frequency        = 2                              # 查落地价 2 次
        user.interaction_price_band   = PriceBand.W20_30.value
        user.inquiry_price_band       = PriceBand.W20_30.value
        user.conversion_stage         = ConversionStage.LEAD.value
        user.test_drive_status        = TestDriveStatus.NOT_DONE.value
    return user


def create_lisi():
    """
    李四：成都（仅限行），年轻新贵，旗舰设备，看过比亚迪汉和奥迪Q2L。
    预期推理结果：绿牌刚需（成都仅限行+看纯电）+ 单人代步。
    """
    onto = get_onto()
    with onto:
        user = onto.User("李四")
        user.age_range                = AgeRange.AGE_24_34.value
        user.gender                   = Gender.FEMALE.value
        user.generation_group         = GenerationGroup.YOUNG_ELITE.value
        user.city_tier                = CityTier.NEW_TIER_1.value
        user.policy_restriction_fuel  = PolicyFuel.RESTRICTED_ROAD.value    # 成都：仅限行
        user.policy_restriction_ev    = PolicyEV.NO_RESTRICTION.value
        user.device_price_tier        = DevicePriceTier.FLAGSHIP.value       # 8000+ 档
        user.travel_activity          = TravelActivity.BASE_MAP_RIDE.value
        user.inquiry_frequency        = 1
        user.interaction_price_band   = PriceBand.W30_50.value
        user.inquiry_price_band       = PriceBand.W30_50.value
        user.conversion_stage         = ConversionStage.NO_LEAD.value
        user.test_drive_status        = TestDriveStatus.NOT_DONE.value
    return user


def create_zhaoliu():
    """
    赵六：二线城市无限制，高频出行，偏好增程/燃油（无纯电交互）。
    预期推理结果：里程焦虑（高频出行 + 规避纯电 + 非绿牌刚需城市）。
    """
    onto = get_onto()
    with onto:
        user = onto.User("赵六")
        user.age_range                = AgeRange.AGE_35_44.value
        user.gender                   = Gender.MALE.value
        user.generation_group         = GenerationGroup.CORE_FAMILY.value
        user.city_tier                = CityTier.TIER_2.value
        user.policy_restriction_fuel  = PolicyFuel.NO_RESTRICTION.value
        user.policy_restriction_ev    = PolicyEV.NO_RESTRICTION.value
        user.device_price_tier        = DevicePriceTier.MID_HIGH.value
        user.travel_activity          = TravelActivity.HIGH_MAP_RIDE.value  # 高频出行
        user.inquiry_frequency        = 1
        user.interaction_price_band   = PriceBand.W30_50.value
        user.inquiry_price_band       = PriceBand.W30_50.value
        user.conversion_stage         = ConversionStage.NO_LEAD.value
        user.test_drive_status        = TestDriveStatus.NOT_DONE.value
    return user


def create_sunqi():
    """
    孙七：北京限牌限行，看过插电混动（无纯电交互）。
    预期推理结果：无桩且限号（限牌城市 + 看 PHEV/EREV 而非纯电）。
    """
    onto = get_onto()
    with onto:
        user = onto.User("孙七")
        user.age_range                = AgeRange.AGE_35_44.value
        user.gender                   = Gender.MALE.value
        user.generation_group         = GenerationGroup.CORE_FAMILY.value
        user.city_tier                = CityTier.TIER_1.value
        user.policy_restriction_fuel  = PolicyFuel.RESTRICTED_BOTH.value
        user.policy_restriction_ev    = PolicyEV.RESTRICTED_PLATE.value
        user.device_price_tier        = DevicePriceTier.MID.value
        user.travel_activity          = TravelActivity.BASE_MAP_RIDE.value
        user.inquiry_frequency        = 1
        user.interaction_price_band   = PriceBand.W20_30.value
        user.inquiry_price_band       = PriceBand.W20_30.value
        user.conversion_stage         = ConversionStage.NO_LEAD.value
        user.test_drive_status        = TestDriveStatus.NOT_DONE.value
    return user


def create_wangwu():
    """
    王五：二线城市无限制，中坚家庭，看过理想L9（增程）和丰田汉兰达（燃油）。
    预期推理结果：牌照自由 + 刚需6至7座。
    """
    onto = get_onto()
    with onto:
        user = onto.User("王五")
        user.age_range                = AgeRange.AGE_45_54.value
        user.gender                   = Gender.MALE.value
        user.generation_group         = GenerationGroup.CORE_FAMILY.value
        user.city_tier                = CityTier.TIER_2.value
        user.policy_restriction_fuel  = PolicyFuel.NO_RESTRICTION.value
        user.policy_restriction_ev    = PolicyEV.NO_RESTRICTION.value
        user.device_price_tier        = DevicePriceTier.MID_HIGH.value       # 3000~5000 档
        user.travel_activity          = TravelActivity.BASE_MAP_RIDE.value
        user.inquiry_frequency        = 1
        user.interaction_price_band   = PriceBand.W30_50.value
        user.inquiry_price_band       = PriceBand.W30_50.value
        user.conversion_stage         = ConversionStage.TEST_DRIVE.value
        user.test_drive_status        = TestDriveStatus.DONE.value
    return user
