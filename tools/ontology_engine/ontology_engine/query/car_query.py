"""
车型查询接口
============
get_car_profile(car_name, backend="memory") → CarProfile

支持双后端：
  - backend="memory"  — Owlready2 内存图
  - backend="graphdb" — GraphDB SPARQL SELECT
"""

from __future__ import annotations

import os

from ontology_engine.query.schemas import CarProfile

_DEFAULT_BACKEND = os.getenv("ONTOLOGY_BACKEND", "memory")
ONTO_NS = os.getenv("ONTOLOGY_IRI", "http://huawei.com/automotive-marketing-ontology#")


def get_car_profile(car_name: str, backend: str = _DEFAULT_BACKEND) -> CarProfile:
    """
    查询指定车型的完整属性。
    供 Agent 在需求推导后进一步核实车型信息。
    """
    if backend == "graphdb":
        return _get_car_profile_graphdb(car_name)
    return _get_car_profile_memory(car_name)


# ── 内存模式 ─────────────────────────────────────────────────────────────

def _get_car_profile_memory(car_name: str) -> CarProfile:
    from ontology_engine.core.ontology_registry import get_onto
    onto = get_onto()
    car  = onto.search_one(iri=f"*#{car_name}")

    if car is None or not isinstance(car, onto.CarModel):
        raise ValueError(f"车型「{car_name}」不存在于本体中")

    return CarProfile(
        name           = car.name,
        power_type     = car.power_type,
        body_type      = car.body_type,
        car_size_level = car.car_size_level,
        car_price_band = car.car_price_band,
        msrp           = car.msrp,
        brand_camp     = car.brand_camp,
    )


# ── GraphDB 模式 ──────────────────────────────────────────────────────────

def _get_car_profile_graphdb(car_name: str) -> CarProfile:
    from ontology_engine.core.graphdb_client import get_graphdb
    client   = get_graphdb()
    ns       = ONTO_NS
    car_iri  = f"{ns}{car_name}"

    prop_rows = client.sparql_select(f"""
        SELECT ?p ?o WHERE {{
            <{car_iri}> ?p ?o .
            FILTER(isLiteral(?o))
        }}
    """)

    if not prop_rows:
        raise ValueError(f"车型「{car_name}」不存在于 GraphDB 中")

    props: dict = {}
    for row in prop_rows:
        local = row["p"].split("#")[-1]
        props[local] = row["o"]

    return CarProfile(
        name           = car_name,
        power_type     = props.get("power_type"),
        body_type      = props.get("body_type"),
        car_size_level = props.get("car_size_level"),
        car_price_band = props.get("car_price_band"),
        msrp           = float(props["msrp"]) if props.get("msrp") else None,
        brand_camp     = props.get("brand_camp"),
    )
