"""
本体单例注册
============
管理全局唯一的 Owlready2 onto 对象。
整个引擎所有模块通过 get_onto() 获取同一个内存本体命名空间，
防止多处 get_ontology() 调用导致命名空间分裂。
"""

from owlready2 import get_ontology, Ontology
from ontology_engine.config.settings import ONTOLOGY_IRI

_onto: Ontology | None = None


def get_onto() -> Ontology:
    """
    获取全局本体单例。首次调用时自动创建，后续调用返回同一对象。
    """
    global _onto
    if _onto is None:
        _onto = get_ontology(ONTOLOGY_IRI)
    return _onto


def reset_onto() -> None:
    """
    重置本体单例（主要用于测试隔离）。
    调用后 get_onto() 将创建全新的本体对象。
    """
    global _onto
    _onto = None
