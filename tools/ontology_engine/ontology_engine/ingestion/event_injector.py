"""
用户行为事件注入器
==================
支持 memory / graphdb 双后端，注入行为事件并可选触发增量推理。

设计要点：
  - inject()：注入单条事件，若 auto_re_infer=True 则自动重推理该用户
  - inject_batch()：批量注入，按用户分组，每个用户只重推一次（高效）
  - Memory 后端：通过 Owlready2 API 直接修改 OWL 实例
  - GraphDB 后端：通过 SPARQL UPDATE DELETE/INSERT 修改三元组
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ontology_engine.ingestion.event_types import UserBehaviorEvent
from ontology_engine.config.settings import ONTOLOGY_IRI

if TYPE_CHECKING:
    from ontology_engine.query.schemas import UserNeedResult

logger = logging.getLogger(__name__)

ONTO_NS = ONTOLOGY_IRI.rstrip("#") + "#"


class EventInjector:
    """
    用户行为事件注入器。

    参数：
        backend      — "memory"（默认） | "graphdb"
        auto_re_infer — 注入后是否自动对该用户触发增量推理（默认 True）
    """

    def __init__(self, backend: str = "memory", auto_re_infer: bool = True):
        self._backend        = backend
        self._auto_re_infer  = auto_re_infer

    # ── 公共接口 ─────────────────────────────────────────────────────────────

    def inject(self, event: UserBehaviorEvent) -> "UserNeedResult | None":
        """
        注入单条行为事件。

        返回：
            若 auto_re_infer=True，返回该用户最新的推理结果；否则返回 None。
        """
        if self._backend == "graphdb":
            self._inject_graphdb(event)
        else:
            self._inject_memory(event)

        if self._auto_re_infer:
            return self._re_infer_user(event.user_id)
        return None

    def inject_batch(
        self, events: list[UserBehaviorEvent]
    ) -> dict[str, "UserNeedResult"]:
        """
        批量注入事件列表。

        按 user_id 分组顺序注入，若 auto_re_infer=True 则每个用户只重推一次。

        返回：
            {user_id: UserNeedResult}（每个出现过的用户一条）
        """
        # 收集所有受影响的用户（保持顺序）
        affected_users: list[str] = []
        seen: set[str] = set()

        for event in events:
            if self._backend == "graphdb":
                self._inject_graphdb(event)
            else:
                self._inject_memory(event)

            if event.user_id not in seen:
                seen.add(event.user_id)
                affected_users.append(event.user_id)

        results: dict[str, "UserNeedResult"] = {}
        if self._auto_re_infer:
            for uid in affected_users:
                result = self._re_infer_user(uid)
                if result is not None:
                    results[uid] = result

        return results

    # ── Memory 后端 ──────────────────────────────────────────────────────────

    def _inject_memory(self, event: UserBehaviorEvent) -> None:
        from ontology_engine.core.ontology_registry import get_onto
        onto = get_onto()

        user = onto.search_one(iri=f"*#{event.user_id}")
        if user is None:
            raise ValueError(
                f"用户 '{event.user_id}' 不存在于本体中，请先调用 load_abox()"
            )

        with onto:
            if event.event_type == "profile_update":
                self._profile_update_memory(user, event.payload)
            elif event.event_type == "car_view":
                self._car_view_memory(user, onto, event.payload)
            elif event.event_type == "journey_event":
                self._journey_event_memory(user, onto, event.payload)

    def _profile_update_memory(self, user, payload: dict) -> None:
        field = payload.get("field")
        value = payload.get("value")
        if not field:
            raise ValueError("profile_update payload 缺少 'field' 字段")
        if not hasattr(user, field):
            raise ValueError(f"User 实例不存在属性 '{field}'")
        setattr(user, field, value)
        logger.debug("Memory: 更新用户 %s 属性 %s = %s", user.name, field, value)

    def _car_view_memory(self, user, onto, payload: dict) -> None:
        car_name = payload.get("car_name")
        if not car_name:
            raise ValueError("car_view payload 缺少 'car_name' 字段")

        # 查找是否已存在同名车型实例
        existing = onto.search_one(iri=f"*#{car_name}")
        if existing is not None:
            car = existing
        else:
            # 动态创建新车型实例
            car = onto.CarModel(car_name)
            for attr in ("power_type", "body_type", "car_price_band",
                         "brand_camp", "car_size_level"):
                if payload.get(attr):
                    setattr(car, attr, payload[attr])

        if car not in user.has_interacted_with:
            user.has_interacted_with.append(car)
            logger.debug("Memory: 为用户 %s 追加看车记录 %s", user.name, car_name)

    def _journey_event_memory(self, user, onto, payload: dict) -> None:
        # 购车链路事件目前仅记录在 DataProperty（或未来扩展的 journey 属性）
        # 当前实现：写入 user.journey_events（若存在），否则仅记录日志
        event_id = payload.get("event_id", "")
        logger.info(
            "Memory: 用户 %s 触发购车链路事件 %s（%s）",
            user.name, event_id, payload.get("event_name", "")
        )

    # ── GraphDB 后端 ─────────────────────────────────────────────────────────

    def _inject_graphdb(self, event: UserBehaviorEvent) -> None:
        from ontology_engine.core.graphdb_client import get_graphdb
        client = get_graphdb()
        ns     = ONTO_NS
        user_iri = f"{ns}{event.user_id}"

        if event.event_type == "profile_update":
            self._profile_update_graphdb(client, user_iri, ns, event.payload)
        elif event.event_type == "car_view":
            self._car_view_graphdb(client, user_iri, ns, event.payload)
        elif event.event_type == "journey_event":
            logger.info(
                "GraphDB: 用户 %s 触发购车链路事件 %s",
                event.user_id, event.payload.get("event_id", "")
            )

    def _profile_update_graphdb(
        self, client, user_iri: str, ns: str, payload: dict
    ) -> None:
        field = payload.get("field")
        value = payload.get("value")
        if not field:
            raise ValueError("profile_update payload 缺少 'field' 字段")

        prop_iri = f"{ns}{field}"
        # DELETE 旧值 + INSERT 新值（原子操作）
        client.sparql_update(f"""
            DELETE {{ <{user_iri}> <{prop_iri}> ?old }}
            INSERT {{ <{user_iri}> <{prop_iri}> "{value}" }}
            WHERE  {{ OPTIONAL {{ <{user_iri}> <{prop_iri}> ?old }} }}
        """)
        logger.debug("GraphDB: 更新用户 %s 属性 %s = %s", user_iri, field, value)

    def _car_view_graphdb(
        self, client, user_iri: str, ns: str, payload: dict
    ) -> None:
        car_name = payload.get("car_name")
        if not car_name:
            raise ValueError("car_view payload 缺少 'car_name' 字段")

        car_iri = f"{ns}{car_name}"

        # 建立看车关系
        triples = [
            (f"<{user_iri}>", f"<{ns}has_interacted_with>", f"<{car_iri}>"),
            (f"<{car_iri}>", "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>",
             f"<{ns}CarModel>"),
        ]
        for attr in ("power_type", "body_type", "car_price_band",
                     "brand_camp", "car_size_level"):
            val = payload.get(attr)
            if val:
                triples.append(
                    (f"<{car_iri}>", f"<{ns}{attr}>", f'"{val}"')
                )
        client.insert_triples(triples)
        logger.debug("GraphDB: 为用户 %s 追加看车记录 %s", user_iri, car_name)

    # ── 增量推理 ─────────────────────────────────────────────────────────────

    def _re_infer_user(self, user_id: str) -> "UserNeedResult | None":
        """清除旧推理结果，对单个用户重新执行全部规则。"""
        try:
            if self._backend == "graphdb":
                return self._re_infer_user_graphdb(user_id)
            return self._re_infer_user_memory(user_id)
        except Exception as exc:
            logger.error("增量推理失败：用户 %s，原因：%s", user_id, exc)
            return None

    def _re_infer_user_memory(self, user_id: str) -> "UserNeedResult":
        from ontology_engine.core.ontology_registry import get_onto
        from ontology_engine.rules.rule_registry import create_default_registry
        from ontology_engine.abox.need_singletons import get_need
        from ontology_engine.query.user_need_query import get_user_needs

        onto = get_onto()
        user = onto.search_one(iri=f"*#{user_id}")
        if user is None:
            raise ValueError(f"用户 '{user_id}' 不存在")

        # 清除旧推理结果
        with onto:
            user.has_inferred_need.clear()

        # 执行所有规则
        rules = create_default_registry().get_ordered_rules()
        with onto:
            for rule in rules:
                triggered_keys = rule.evaluate(user)
                for key in triggered_keys:
                    need_instance = get_need(key)
                    if need_instance not in user.has_inferred_need:
                        user.has_inferred_need.append(need_instance)

        return get_user_needs(user, backend="memory")

    def _re_infer_user_graphdb(self, user_id: str) -> "UserNeedResult":
        from ontology_engine.core.graphdb_client import get_graphdb
        from ontology_engine.rules.reasoner import _build_user_proxy, _need_key_to_local
        from ontology_engine.rules.rule_registry import create_default_registry
        from ontology_engine.query.user_need_query import get_user_needs

        client   = get_graphdb()
        ns       = ONTO_NS
        user_iri = f"{ns}{user_id}"

        # 清除旧推理结果
        client.sparql_update(f"""
            DELETE {{ <{user_iri}> <{ns}has_inferred_need> ?need }}
            WHERE  {{ <{user_iri}> <{ns}has_inferred_need> ?need }}
        """)

        # 执行所有规则
        rules = create_default_registry().get_ordered_rules()
        proxy = _build_user_proxy(client, user_iri)

        for rule in rules:
            triggered_keys = rule.evaluate(proxy)
            if triggered_keys:
                triples = [
                    (f"<{user_iri}>",
                     f"<{ns}has_inferred_need>",
                     f"<{ns}{_need_key_to_local(key)}>")
                    for key in triggered_keys
                ]
                client.insert_triples(triples)
                # 更新 proxy 的 has_inferred_need 以支持后续规则的互斥检查
                from ontology_engine.rules.reasoner import _NeedProxy
                for key in triggered_keys:
                    need_iri = f"{ns}{_need_key_to_local(key)}"
                    proxy.has_inferred_need.append(_NeedProxy(need_iri))

        return get_user_needs(user_id, backend="graphdb")
