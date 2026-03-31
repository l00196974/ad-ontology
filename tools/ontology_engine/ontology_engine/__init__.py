"""
汽车营销本体推理引擎 (Automotive Marketing Ontology Engine)
===========================================================

快速使用：

    from ontology_engine import build_tbox, load_abox, Reasoner, get_user_needs

    build_tbox()        # 构建 OWL 模式层（类 + 属性）
    load_abox()         # 加载实例数据（用户 + 车型 + 看车关系）
    Reasoner().run()    # 执行推理规则，写入 has_inferred_need 边
    result = get_user_needs("张三")   # 查询推导结果
    print(result.inferred_needs)     # → [InferredNeed(need_label='绿牌刚需/有桩无畏', ...)]

模块层次（由下至上，单向依赖）：
    config/  →  core/  →  tbox/  →  abox/  →  rules/  →  query/
                                    journey/  ↗
"""

__version__ = "1.1.0"

from ontology_engine.tbox.tbox_builder     import build_tbox
from ontology_engine.abox.abox_loader      import load_abox
from ontology_engine.abox.abox_exporter    import export_and_upload, export_to_ntriples
from ontology_engine.rules.reasoner        import Reasoner
from ontology_engine.rules.rule_updater    import RuleUpdater
from ontology_engine.query.user_need_query import get_user_needs, get_user_needs_json
from ontology_engine.query.car_query       import get_car_profile
from ontology_engine.query.journey_query   import get_user_journey
from ontology_engine.core.ontology_registry import get_onto, reset_onto
from ontology_engine.core.graphdb_client   import get_graphdb, reset_graphdb
from ontology_engine.ingestion.event_types    import UserBehaviorEvent
from ontology_engine.ingestion.event_injector import EventInjector
from ontology_engine.ingestion.batch_injector import inject_from_json, inject_from_dict
from ontology_engine.serving.inference_service import InferenceService

__all__ = [
    # 核心推理
    "build_tbox", "load_abox",
    "export_and_upload", "export_to_ntriples",
    "Reasoner",
    # 规则管理
    "RuleUpdater",
    # 查询
    "get_user_needs", "get_user_needs_json",
    "get_car_profile",
    "get_user_journey",
    # 后端管理
    "get_onto", "reset_onto",
    "get_graphdb", "reset_graphdb",
    # 行为注入
    "UserBehaviorEvent", "EventInjector",
    "inject_from_json", "inject_from_dict",
    # 在线推理
    "InferenceService",
]
