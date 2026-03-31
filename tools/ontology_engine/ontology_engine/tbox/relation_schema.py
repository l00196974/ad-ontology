"""
关系属性 TBox 模式定义（Object Properties）
===========================================
定义连接 User、CarModel、MarketingNeed 三类节点的有向边。

本体区别于关系数据库的核心在于：关系本身是一等公民（First-Class Citizen），
可以参与推理规则的前提（antecedent）和结论（consequent）。
独立定义关系属性文件，使图谱的"边类型"清晰可见。
"""

from owlready2 import ObjectProperty
from ontology_engine.core.ontology_registry import get_onto


def build_relation_schema() -> None:
    """
    在 onto 上下文中定义全部对象属性（图谱的有向边）。
    """
    onto = get_onto()
    with onto:
        User         = onto.User
        CarModel     = onto.CarModel
        MarketingNeed = onto.MarketingNeed

        class has_interacted_with(ObjectProperty):
            """
            用户←→车型的交互行为关系（看车行为）。
            Domain: User → Range: CarModel
            来源：汽车垂媒日志（搜索/浏览/详情查阅/车型对比/查落地价等行为）。
            ⚡ 推理规则的核心输入边：牌照刚需/里程焦虑规则均依赖此边上的车型属性。
            """
            domain = [User]
            range  = [CarModel]

        class has_inferred_need(ObjectProperty):
            """
            推理机推导出的营销需求关系。
            Domain: User → Range: MarketingNeed
            ⚠️ 此边完全由推理规则自动生成，不应手工录入 ABox。
            Agent 调用 get_user_needs() 时读取的核心输出边。
            """
            domain = [User]
            range  = [MarketingNeed]

        class is_need_of(ObjectProperty):
            """
            has_inferred_need 的逆关系（Inverse Property）。
            Domain: MarketingNeed → Range: User
            用途：从需求视角反查"哪些用户持有此需求"，
            支持营销触达场景下的人群圈选。
            """
            inverse_property = has_inferred_need
            domain = [MarketingNeed]
            range  = [User]
