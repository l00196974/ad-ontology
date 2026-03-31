"""
用户需求查询接口（核心 Agent 接口）
=====================================
get_user_needs(user_instance | user_name, backend="memory") → UserNeedResult

支持双后端：
  - backend="memory"  — Owlready2 内存图（开发/测试）
  - backend="graphdb" — GraphDB SPARQL SELECT（生产）
"""

from __future__ import annotations

import dataclasses
import os

from ontology_engine.query.schemas import UserNeedResult, UserProfile, CarInteraction, InferredNeed

_DEFAULT_BACKEND = os.getenv("ONTOLOGY_BACKEND", "memory")
ONTO_NS = os.getenv("ONTOLOGY_IRI", "http://huawei.com/automotive-marketing-ontology#")


def get_user_needs(user_instance, backend: str = _DEFAULT_BACKEND) -> UserNeedResult:
    """
    【核心 Agent 接口】查询用户所有被推导出的营销需求标签。

    参数：
        user_instance: User OWL 实例、用户名字符串 或（graphdb 模式下）用户 IRI
        backend:       "memory"（默认） | "graphdb"

    返回：
        UserNeedResult（含原始画像、看车记录、推导需求列表）
    """
    if backend == "graphdb":
        return _get_user_needs_graphdb(user_instance)
    return _get_user_needs_memory(user_instance)


def get_user_needs_json(user_instance, backend: str = _DEFAULT_BACKEND) -> dict:
    """等价于 get_user_needs()，但返回 JSON 可序列化的 dict。"""
    result = get_user_needs(user_instance, backend)
    return dataclasses.asdict(result)


# ── 内存模式（Owlready2）─────────────────────────────────────────────────

def _get_user_needs_memory(user_instance) -> UserNeedResult:
    from ontology_engine.core.ontology_registry import get_onto
    onto = get_onto()

    if isinstance(user_instance, str):
        user_instance = onto.search_one(iri=f"*#{user_instance}")
        if user_instance is None:
            raise ValueError("用户不存在于本体中，请先调用 load_abox()")

    if not isinstance(user_instance, onto.User):
        raise TypeError("传入的实例不是 User 类型")

    raw_profile = UserProfile(
        age_range         = user_instance.age_range,
        gender            = user_instance.gender,
        generation_group  = user_instance.generation_group,
        city_tier         = user_instance.city_tier,
        policy_fuel       = user_instance.policy_restriction_fuel,
        policy_ev         = user_instance.policy_restriction_ev,
        device_price_tier = user_instance.device_price_tier,
        travel_activity   = user_instance.travel_activity,
        inquiry_frequency = user_instance.inquiry_frequency,
        conversion_stage  = user_instance.conversion_stage,
    )

    interacted_cars = [
        CarInteraction(
            name           = car.name,
            power_type     = car.power_type,
            body_type      = car.body_type,
            car_price_band = car.car_price_band,
            brand_camp     = car.brand_camp,
        )
        for car in user_instance.has_interacted_with
    ]

    inferred_needs = []
    for need in user_instance.has_inferred_need:
        cls = type(need)
        inferred_needs.append(InferredNeed(
            need_label  = getattr(cls, "need_label", need.name),
            need_class  = cls.__name__,
            category    = getattr(cls, "category", "其他"),
            instance_id = need.name,
        ))

    return UserNeedResult(
        user            = user_instance.name,
        raw_profile     = raw_profile,
        interacted_cars = interacted_cars,
        inferred_needs  = inferred_needs,
        need_count      = len(inferred_needs),
    )


# ── GraphDB 模式（SPARQL SELECT）────────────────────────────────────────

def _get_user_needs_graphdb(user_ref) -> UserNeedResult:
    from ontology_engine.core.graphdb_client import get_graphdb
    client = get_graphdb()
    ns = ONTO_NS

    # 解析用户 IRI
    if not str(user_ref).startswith("http"):
        user_iri = f"{ns}{user_ref}"
    else:
        user_iri = str(user_ref)

    user_name = user_iri.split("#")[-1]

    # 查询用户 DataProperty
    prop_rows = client.sparql_select(f"""
        SELECT ?p ?o WHERE {{
            <{user_iri}> ?p ?o .
            FILTER(isLiteral(?o))
        }}
    """)
    props: dict = {}
    for row in prop_rows:
        local = row["p"].split("#")[-1]
        props[local] = row["o"]

    raw_profile = UserProfile(
        age_range         = props.get("age_range"),
        gender            = props.get("gender"),
        generation_group  = props.get("generation_group"),
        city_tier         = props.get("city_tier"),
        policy_fuel       = props.get("policy_restriction_fuel"),
        policy_ev         = props.get("policy_restriction_ev"),
        device_price_tier = props.get("device_price_tier"),
        travel_activity   = props.get("travel_activity"),
        inquiry_frequency = int(props["inquiry_frequency"]) if props.get("inquiry_frequency") else None,
        conversion_stage  = props.get("conversion_stage"),
    )

    # 查询看车记录
    car_rows = client.sparql_select(f"""
        SELECT ?car ?p ?o WHERE {{
            <{user_iri}> <{ns}has_interacted_with> ?car .
            ?car ?p ?o .
            FILTER(isLiteral(?o))
        }}
    """)
    cars_dict: dict[str, dict] = {}
    for row in car_rows:
        car_iri = row["car"]
        if car_iri not in cars_dict:
            cars_dict[car_iri] = {"name": car_iri.split("#")[-1]}
        local = row["p"].split("#")[-1]
        cars_dict[car_iri][local] = row["o"]

    interacted_cars = [
        CarInteraction(
            name           = v["name"],
            power_type     = v.get("power_type"),
            body_type      = v.get("body_type"),
            car_price_band = v.get("car_price_band"),
            brand_camp     = v.get("brand_camp"),
        )
        for v in cars_dict.values()
    ]

    # 查询推导需求（has_inferred_need + 需求类元数据）
    # OWL RL 推理会产生父类断言，用 NOT EXISTS 过滤只保留叶子类（最具体的需求类）
    need_rows = client.sparql_select(f"""
        SELECT DISTINCT ?need ?need_class WHERE {{
            <{user_iri}> <{ns}has_inferred_need> ?need .
            ?need a ?need_class .
            FILTER(STRSTARTS(STR(?need_class), "{ns}"))
            FILTER NOT EXISTS {{
                ?need a ?sub_class .
                ?sub_class <http://www.w3.org/2000/01/rdf-schema#subClassOf> ?need_class .
                FILTER(?sub_class != ?need_class)
                FILTER(STRSTARTS(STR(?sub_class), "{ns}"))
            }}
        }}
    """)

    inferred_needs = []
    for row in need_rows:
        need_class  = row.get("need_class", "").split("#")[-1]
        instance_id = row.get("need", "").split("#")[-1]
        need_label  = _fallback_label(need_class)
        category    = _fallback_category(need_class)
        inferred_needs.append(InferredNeed(
            need_label  = need_label,
            need_class  = need_class,
            category    = category,
            instance_id = instance_id,
        ))

    return UserNeedResult(
        user            = user_name,
        raw_profile     = raw_profile,
        interacted_cars = interacted_cars,
        inferred_needs  = inferred_needs,
        need_count      = len(inferred_needs),
    )


# ── 元数据回退表（GraphDB 中若无 OWL 注解则使用此表）────────────────────

_LABEL_MAP: dict[str, str] = {
    "GreenPlateRequired":    "绿牌刚需/有桩无畏",
    "NoParkingLimitNumber":  "无桩且限号/刚需PHEV",
    "LicenseFree":           "牌照自由/动力无忧",
    "SixSevenSeatsRequired": "刚需6至7座",
    "SinglePersonCommute":   "单人代步/颜值优先",
    "BudgetLocked":          "预算死锁/价格敏感",
    "FlexibleBudget":        "弹性预算/品牌溢价",
    "RangeMileageAnxiety":   "严重里程焦虑",
    "LongCommuteUser":       "通勤距离增加用户",
}

_CATEGORY_MAP: dict[str, str] = {
    "GreenPlateRequired":    "牌照刚需",
    "NoParkingLimitNumber":  "牌照刚需",
    "LicenseFree":           "牌照自由",
    "SixSevenSeatsRequired": "空间刚需",
    "SinglePersonCommute":   "空间刚需",
    "BudgetLocked":          "预算敏感",
    "FlexibleBudget":        "预算敏感",
    "RangeMileageAnxiety":   "补能焦虑",
    "LongCommuteUser":       "通勤行为",
}


def _fallback_label(need_class: str) -> str:
    return _LABEL_MAP.get(need_class, need_class)


def _fallback_category(need_class: str) -> str:
    return _CATEGORY_MAP.get(need_class, "其他")
