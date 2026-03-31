"""
推理引擎主类
============
支持双后端：
  - backend="memory"  — Owlready2 内存图（开发/测试，零依赖）
  - backend="graphdb" — GraphDB SPARQL（生产，持久化 + OWL RL）

内存模式：
  遍历所有 User 实例，按拓扑有序规则逐一执行，
  将结果写回 ABox（has_inferred_need 边）。

GraphDB 模式：
  通过 SPARQL SELECT 查询用户属性和看车记录，
  调用 rule.evaluate_sparql()（或回退到内存属性读取），
  通过 SPARQL UPDATE 将推理结果写回 GraphDB。
"""

from __future__ import annotations

import logging

from ontology_engine.core.ontology_registry import get_onto
from ontology_engine.abox.need_singletons import get_need
from ontology_engine.rules.rule_registry import RuleRegistry, create_default_registry
from ontology_engine.config.enums import NeedKey
from ontology_engine.config.settings import ONTOLOGY_IRI

logger = logging.getLogger(__name__)

ONTO_NS = ONTOLOGY_IRI.rstrip("#") + "#"


class Reasoner:
    """
    汽车营销本体推理引擎。

    参数：
        registry: 自定义规则注册表（测试时可传入只含部分规则的注册表）
        backend:  "memory"（默认） | "graphdb"
    """

    def __init__(
        self,
        registry: RuleRegistry | None = None,
        backend: str = "memory",
    ):
        self._registry = registry or create_default_registry()
        self._backend  = backend

    def run(self) -> list[dict]:
        """
        对 ABox 中所有 User 实例执行完整推理。

        返回：
            所有规则的触发日志列表
        """
        if self._backend == "graphdb":
            return self._run_graphdb()
        return self._run_memory()

    # ── 内存模式（Owlready2）──────────────────────────────────────────────

    def _run_memory(self) -> list[dict]:
        onto      = get_onto()
        all_users = list(onto.User.instances())
        rules     = self._registry.get_ordered_rules()

        print("\n[推理引擎] 开始执行业务规则推导（memory 模式）...")
        print(f"  规则执行顺序：{[r.rule_id for r in rules]}")
        print("=" * 60)

        for user in all_users:
            print(f"\n  处理用户：「{user.name}」")
            for rule in rules:
                triggered_keys = rule.evaluate(user)
                with onto:
                    for key in triggered_keys:
                        need_instance = get_need(key)
                        if need_instance not in user.has_inferred_need:
                            user.has_inferred_need.append(need_instance)

        print("=" * 60)
        print(f"[推理引擎] 推导完成，共处理 {len(all_users)} 个用户")
        return self._registry.all_logs()

    # ── GraphDB 模式（SPARQL）────────────────────────────────────────────

    def _run_graphdb(self) -> list[dict]:
        from ontology_engine.core.graphdb_client import get_graphdb

        client = get_graphdb()
        rules  = self._registry.get_ordered_rules()

        logger.info("[推理引擎] 开始执行业务规则推导（graphdb 模式）...")
        logger.info("规则执行顺序：%s", [r.rule_id for r in rules])

        # 查询所有 User IRI
        user_iri_col = client.sparql_select(
            f"SELECT ?user WHERE {{ ?user a <{ONTO_NS}User> }}"
        )
        user_iris = [row["user"] for row in user_iri_col]

        logger.info("共找到 %d 个用户", len(user_iris))

        for user_iri in user_iris:
            user_name = user_iri.split("#")[-1]
            logger.debug("处理用户：%s", user_name)

            for rule in rules:
                triggered_need_iris = self._evaluate_rule_graphdb(
                    client, rule, user_iri
                )
                if triggered_need_iris:
                    triples = [
                        (f"<{user_iri}>",
                         f"<{ONTO_NS}has_inferred_need>",
                         f"<{need_iri}>")
                        for need_iri in triggered_need_iris
                    ]
                    client.insert_triples(triples)

        logger.info("[推理引擎] 推导完成，共处理 %d 个用户", len(user_iris))
        return self._registry.all_logs()

    def _evaluate_rule_graphdb(
        self,
        client,
        rule,
        user_iri: str,
    ) -> list[str]:
        """
        尝试调用 rule.evaluate_sparql()；
        若未实现，回退到内存属性读取（从 GraphDB SELECT 重建属性 dict）。
        """
        try:
            return rule.evaluate_sparql(client, user_iri)
        except NotImplementedError:
            pass

        # 回退：从 GraphDB 读取用户属性，构造轻量 UserProxy，调用 evaluate()
        proxy = _build_user_proxy(client, user_iri)
        triggered_keys: list[NeedKey] = rule.evaluate(proxy)

        # 将 NeedKey → need IRI
        return [
            f"{ONTO_NS}{_need_key_to_local(key)}"
            for key in triggered_keys
        ]


# ── 辅助：从 GraphDB 重建用户属性代理 ────────────────────────────────────

def _need_key_to_local(key: NeedKey) -> str:
    """NeedKey 枚举 → OWL 实例 local name（与 need_singletons 对应）"""
    mapping = {
        NeedKey.GREEN_PLATE:     "need_绿牌刚需",
        NeedKey.NO_PARKING:      "need_无桩且限号",
        NeedKey.LICENSE_FREE:    "need_牌照自由",
        NeedKey.SIX_SEVEN_SEATS: "need_刚需6至7座",
        NeedKey.SINGLE_COMMUTE:  "need_单人代步",
        NeedKey.BUDGET_LOCKED:   "need_预算死锁",
        NeedKey.FLEXIBLE_BUDGET: "need_弹性预算",
        NeedKey.RANGE_ANXIETY:   "need_里程焦虑",
        NeedKey.LONG_COMMUTE:    "need_通勤距离增加",
    }
    return mapping[key]


class _UserProxy:
    """
    轻量级用户属性代理，供回退模式下规则的 evaluate(user) 使用。
    从 GraphDB SPARQL SELECT 结果重建，接口与 Owlready2 User 实例兼容。
    """
    def __init__(self, props: dict, cars: list, inferred_needs: list):
        self.name                    = props.get("name", "")
        self.age_range               = props.get("age_range")
        self.gender                  = props.get("gender")
        self.generation_group        = props.get("generation_group")
        self.city_tier               = props.get("city_tier")
        self.policy_restriction_fuel = props.get("policy_restriction_fuel")
        self.policy_restriction_ev   = props.get("policy_restriction_ev")
        self.device_price_tier       = props.get("device_price_tier")
        self.travel_activity         = props.get("travel_activity")
        self.inquiry_frequency       = int(props["inquiry_frequency"]) if props.get("inquiry_frequency") else 0
        self.interaction_price_band  = props.get("interaction_price_band")
        self.inquiry_price_band      = props.get("inquiry_price_band")
        self.conversion_stage        = props.get("conversion_stage")
        self.test_drive_status       = props.get("test_drive_status")
        self.has_interacted_with     = cars
        self.has_inferred_need       = inferred_needs


class _CarProxy:
    """轻量级车辆属性代理"""
    def __init__(self, props: dict):
        self.name          = props.get("name", "")
        self.power_type    = props.get("power_type")
        self.body_type     = props.get("body_type")
        self.car_price_band = props.get("car_price_band")
        self.car_size_level = props.get("car_size_level")
        self.brand_camp    = props.get("brand_camp")


class _NeedProxy:
    """轻量级需求代理（用于 has_inferred_need 互斥检查）"""
    def __init__(self, iri: str):
        self._iri = iri

    def __eq__(self, other):
        if isinstance(other, _NeedProxy):
            return self._iri == other._iri
        # 与 Owlready2 实例比较：通过 IRI 或 name 匹配
        # get_need() 返回的 Owlready2 实例有 .iri 属性（完整 IRI）和 .name 属性（local name）
        if hasattr(other, "iri"):
            return self._iri == other.iri
        if hasattr(other, "name"):
            local = self._iri.split("#")[-1]
            return local == other.name
        return False

    def __hash__(self):
        return hash(self._iri)


def _build_user_proxy(client, user_iri: str) -> _UserProxy:
    """从 GraphDB 查询用户所有属性，重建 _UserProxy。"""
    ns = ONTO_NS

    # 查用户 DataProperty
    prop_rows = client.sparql_select(f"""
        SELECT ?p ?o WHERE {{
            <{user_iri}> ?p ?o .
            FILTER(isLiteral(?o))
        }}
    """)
    props: dict = {"name": user_iri.split("#")[-1]}
    for row in prop_rows:
        local = row["p"].split("#")[-1]
        props[local] = row["o"]

    # 查看车记录
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
    cars = [_CarProxy(v) for v in cars_dict.values()]

    # 查已推导需求（用于互斥检查）
    need_rows = client.sparql_select(f"""
        SELECT ?need WHERE {{
            <{user_iri}> <{ns}has_inferred_need> ?need .
        }}
    """)
    needs = [_NeedProxy(row["need"]) for row in need_rows]

    return _UserProxy(props, cars, needs)
