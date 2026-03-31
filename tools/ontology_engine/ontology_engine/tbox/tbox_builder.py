"""
TBox 构建编排器
===============
按照依赖顺序统一调用各 schema 模块，完成完整的 TBox 构建。

依赖顺序：
  1. need_schema（MarketingNeed 类层次，无依赖）
  2. user_schema（User + DataProperty，无依赖）
  3. car_schema（CarModel + DataProperty，无依赖）
  4. relation_schema（ObjectProperty，依赖上述三个类已存在）
"""

from ontology_engine.tbox.need_schema import build_need_schema
from ontology_engine.tbox.user_schema import build_user_schema
from ontology_engine.tbox.car_schema import build_car_schema
from ontology_engine.tbox.relation_schema import build_relation_schema
from ontology_engine.core.ontology_registry import get_onto


def build_tbox() -> None:
    """
    构建完整 TBox（模式层）。

    执行后，onto 对象中将包含：
      - 3 个顶层实体类（User, CarModel, MarketingNeed）
      - MarketingNeed 的 8+ 个子类（带 need_label/category 元数据）
      - 17 个 User DataProperty
      - 6 个 CarModel DataProperty
      - 3 个 ObjectProperty（图谱边）
    """
    build_need_schema()
    build_user_schema()
    build_car_schema()
    build_relation_schema()

    onto = get_onto()
    classes    = [cls.name for cls in onto.classes()]
    data_props = [p.name for p in onto.data_properties()]
    obj_props  = [p.name for p in onto.object_properties()]

    print("[TBox] 模式层构建完成")
    print(f"  实体类（{len(classes)}）：{classes}")
    print(f"  数据属性（{len(data_props)}）：{data_props}")
    print(f"  对象属性（{len(obj_props)}）：{obj_props}")
