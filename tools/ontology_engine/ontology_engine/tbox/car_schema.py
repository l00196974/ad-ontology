"""
CarModel TBox 模式定义
======================
定义 CarModel OWL 类及其 6 个数据属性（DataProperty）。
所有可映射维度均有数据来源注释，不可映射维度预留属性位置。
"""

from owlready2 import Thing, DataProperty, FunctionalProperty
from ontology_engine.core.ontology_registry import get_onto


def build_car_schema() -> type:
    """
    在 onto 上下文中定义 CarModel 类及全部数据属性。
    返回 CarModel 类。
    """
    onto = get_onto()
    with onto:

        class CarModel(Thing):
            """
            汽车本体。
            代表一款具体车型（如：比亚迪汉、丰田汉兰达）。
            TBox 维度覆盖：车身类型、动力类型、价格带、品牌阵营等。
            """
            pass

        # ── 车身 ──────────────────────────────────────────────────────────────

        class body_type(DataProperty, FunctionalProperty):
            """
            车身结构分类。枚举：BodyType。
            来源：标准车型库"级别"字段（轿车/SUV/MPV/跑车/皮卡/微面/轻客）。
            """
            domain = [CarModel]; range = [str]

        class car_size_level(DataProperty, FunctionalProperty):
            """
            通用尺寸级别。枚举：CarSizeLevel。
            来源：标准车型库"车型级别"字段（A00/A0/A/B/C/D）。
            当前数据可行性：否（注释保留扩展位）。
            """
            domain = [CarModel]; range = [str]

        # ── 价格 ──────────────────────────────────────────────────────────────

        class msrp(DataProperty, FunctionalProperty):
            """
            官方建议零售价（元）。
            来源：标准车型库官方报价。若仅到车系粒度，取价格区间中位数。
            示例：209800.0（比亚迪汉 EV 荣耀版起售价）。
            """
            domain = [CarModel]; range = [float]

        class car_price_band(DataProperty, FunctionalProperty):
            """
            车辆价格带。枚举：PriceBand。
            与"人的本体-预算区间"枚举值保持绝对一致，便于推理规则直接比较。
            来源：msrp 分档映射。
            """
            domain = [CarModel]; range = [str]

        # ── 动力 ──────────────────────────────────────────────────────────────

        class power_type(DataProperty, FunctionalProperty):
            """
            驱动能源类型。枚举：PowerType。
            来源：标准车型库"能源类型"字段。
            核心推理输入维度（牌照刚需、里程焦虑规则的关键字段）。
            """
            domain = [CarModel]; range = [str]

        # ── 品牌 ──────────────────────────────────────────────────────────────

        class brand_camp(DataProperty, FunctionalProperty):
            """
            品牌阵营。枚举：BrandCamp。
            来源：品牌阵营映射表（品牌名→阵营，由业务侧预定义）。
            """
            domain = [CarModel]; range = [str]

    return onto.CarModel
