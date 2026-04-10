"""
Item TBox — 产品本体（CarModel 为示例，可扩展）
"""
from __future__ import annotations

from owlready2 import Thing, DataProperty, FunctionalProperty, ObjectProperty

from neotrace.ontology.registry import get_onto


def build_item_schema() -> type:
    onto = get_onto()
    with onto:

        class Brand(Thing):
            """品牌（华为/比亚迪/理想...）"""
            pass

        class Product(Thing):
            """产品线（问界/智界/...）"""
            pass

        class Item(Thing):
            """产品基类（可扩展：车型/手机/服务...）"""
            item_name: str = ""
            item_category: str = ""

        class CarModel(Item):
            """汽车车型（Item 的具体实现示例）"""
            pass

        # ── 品牌关系 ──────────────────────────────────────────────────────────
        class belongs_to_brand(ObjectProperty, FunctionalProperty):
            domain = [Item]; range = [Brand]

        class belongs_to_product(ObjectProperty, FunctionalProperty):
            domain = [CarModel]; range = [Product]

        # ── 金融属性 ──────────────────────────────────────────────────────────
        class msrp(DataProperty, FunctionalProperty):
            """官方指导价（万元）"""
            domain = [CarModel]; range = [float]

        class price_band(DataProperty, FunctionalProperty):
            """价格带（10万以下/10-20万/20-30万/30-50万/50-100万/100万以上）"""
            domain = [CarModel]; range = [str]

        class down_payment_ratio(DataProperty, FunctionalProperty):
            """首付比例（%）"""
            domain = [CarModel]; range = [float]

        class loan_term_months(DataProperty, FunctionalProperty):
            """贷款期限（月）"""
            domain = [CarModel]; range = [int]

        class manufacturer_subsidy(DataProperty, FunctionalProperty):
            """厂商贴息金额（万元）"""
            domain = [CarModel]; range = [float]

        class residual_value_rate(DataProperty, FunctionalProperty):
            """整车保值率（%，3年）"""
            domain = [CarModel]; range = [float]

        # ── 动力属性 ──────────────────────────────────────────────────────────
        class power_type(DataProperty, FunctionalProperty):
            """动力类型（纯电动/插混/增程/燃油/混动）"""
            domain = [CarModel]; range = [str]

        class battery_type(DataProperty, FunctionalProperty):
            """电池类型及高压平台"""
            domain = [CarModel]; range = [str]

        class max_power_kw(DataProperty, FunctionalProperty):
            """最大功率（kW）"""
            domain = [CarModel]; range = [float]

        class zero_to_hundred(DataProperty, FunctionalProperty):
            """零百加速（秒）"""
            domain = [CarModel]; range = [float]

        class pure_ev_range_km(DataProperty, FunctionalProperty):
            """纯电续航（km）"""
            domain = [CarModel]; range = [float]

        class fuel_consumption_per100km(DataProperty, FunctionalProperty):
            """燃油百公里油耗（L）"""
            domain = [CarModel]; range = [float]

        class fast_charge_minutes(DataProperty, FunctionalProperty):
            """快充时长（分钟，30%→80%）"""
            domain = [CarModel]; range = [float]

        class v2l_power_kw(DataProperty, FunctionalProperty):
            """对外放电功率（kW）"""
            domain = [CarModel]; range = [float]

        # ── 车身属性 ──────────────────────────────────────────────────────────
        class body_type(DataProperty, FunctionalProperty):
            """车身类型（轿车/SUV/MPV/跑车/皮卡）"""
            domain = [CarModel]; range = [str]

        class car_size_level(DataProperty, FunctionalProperty):
            """车身级别（微型A00/小型A0/紧凑A/中型B/中大C/大型D）"""
            domain = [CarModel]; range = [str]

        class seat_layout(DataProperty, FunctionalProperty):
            """车内座椅布局（5座/6座/7座）"""
            domain = [CarModel]; range = [str]

        class wheelbase_mm(DataProperty, FunctionalProperty):
            """车身轴距（mm）"""
            domain = [CarModel]; range = [float]

        class door_type(DataProperty, FunctionalProperty):
            """车门形态（普通/电动滑移/剪刀门）"""
            domain = [CarModel]; range = [str]

        # ── 配置属性 ──────────────────────────────────────────────────────────
        class seat_material(DataProperty, FunctionalProperty):
            """座椅材质（真皮/仿皮/织物）"""
            domain = [CarModel]; range = [str]

        class seat_features(DataProperty, FunctionalProperty):
            """座椅功能（加热/通风/按摩）"""
            domain = [CarModel]; range = [str]

        class suspension_type(DataProperty, FunctionalProperty):
            """悬挂结构（独立/非独立/空气悬架）"""
            domain = [CarModel]; range = [str]

        class audio_system(DataProperty, FunctionalProperty):
            """座舱音响与声学配置"""
            domain = [CarModel]; range = [str]

        class trunk_volume_liters(DataProperty, FunctionalProperty):
            """后备箱常规容积（L）"""
            domain = [CarModel]; range = [float]

        # ── 智能属性 ──────────────────────────────────────────────────────────
        class noa_level(DataProperty, FunctionalProperty):
            """智能驾驶等级（L2/L2+/L3）"""
            domain = [CarModel]; range = [str]

        class has_lidar(DataProperty, FunctionalProperty):
            """是否配备激光雷达"""
            domain = [CarModel]; range = [bool]

        class car_phone_ecosystem(DataProperty, FunctionalProperty):
            """手车互联与底层生态（华为鸿蒙/苹果CarPlay/安卓Auto）"""
            domain = [CarModel]; range = [str]

        class hmi_capability(DataProperty, FunctionalProperty):
            """车机系统能力描述"""
            domain = [CarModel]; range = [str]

        # ── 安全属性 ──────────────────────────────────────────────────────────
        class airbag_count(DataProperty, FunctionalProperty):
            """安全气囊数量"""
            domain = [CarModel]; range = [int]

        class high_strength_steel_ratio(DataProperty, FunctionalProperty):
            """车身高强度钢占比（%）"""
            domain = [CarModel]; range = [float]

        class active_safety_features(DataProperty, FunctionalProperty):
            """主动安全配置（AEB/LKA/BSD 等，逗号分隔）"""
            domain = [CarModel]; range = [str]

        class has_360_camera(DataProperty, FunctionalProperty):
            """是否配备全景倒车影像"""
            domain = [CarModel]; range = [bool]

        # ── 品牌/交付属性 ─────────────────────────────────────────────────────
        class brand_tier(DataProperty, FunctionalProperty):
            """品牌层级（豪华/高端/主流/经济）"""
            domain = [CarModel]; range = [str]

        class warranty_policy(DataProperty, FunctionalProperty):
            """整车质保政策（如 5年/10万公里）"""
            domain = [CarModel]; range = [str]

        class delivery_weeks(DataProperty, FunctionalProperty):
            """车辆交付周期（周）"""
            domain = [CarModel]; range = [int]

    return onto.CarModel
