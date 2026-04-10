"""
本体注册中心
"""
from __future__ import annotations
try:
    from owlready2 import get_ontology, default_world
    _OWLREADY_AVAILABLE = True
except ImportError:
    _OWLREADY_AVAILABLE = False
    get_ontology = None  # type: ignore

_ONTO_IRI = "http://neotrace.huawei.com/ad-ontology#"
_onto = None


def get_onto():
    global _onto
    if not _OWLREADY_AVAILABLE:
        return None
    if _onto is None:
        _onto = get_ontology(_ONTO_IRI)
    return _onto


class OntologyRegistry:

    def __init__(self):
        self._onto = get_onto()

    def get_onto(self):
        return self._onto

    def save(self, path: str) -> None:
        self._onto.save(file=path, format="rdfxml")
        print(f"[OntologyRegistry] 本体已保存至 {path}")
