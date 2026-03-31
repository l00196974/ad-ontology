"""
ingestion 模块
"""

from ontology_engine.ingestion.event_types   import UserBehaviorEvent
from ontology_engine.ingestion.event_injector import EventInjector
from ontology_engine.ingestion.batch_injector import inject_from_json, inject_from_dict

__all__ = [
    "UserBehaviorEvent",
    "EventInjector",
    "inject_from_json",
    "inject_from_dict",
]
