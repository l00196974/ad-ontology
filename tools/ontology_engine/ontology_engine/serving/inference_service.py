"""
在线推理服务（函数接口层）
==========================
InferenceService 提供单用户实时推理，适合以下场景：
  - 用户在 App 内发生行为事件，需立即返回最新营销标签
  - Agent 工作流中需要实时获取最新推理结果
  - 联合 EventInjector 实现"注入即推理"

缓存策略：
  - force_refresh=False：若用户已有 has_inferred_need 结果，直接返回（不重推）
  - force_refresh=True ：清除旧结果，强制重新推理
"""

from __future__ import annotations

import logging
import os

from ontology_engine.config.settings import ONTOLOGY_IRI

logger = logging.getLogger(__name__)

ONTO_NS = ONTOLOGY_IRI.rstrip("#") + "#"
_DEFAULT_BACKEND = os.getenv("ONTOLOGY_BACKEND", "memory")


class InferenceService:
    """
    单用户在线推理服务。

    参数：
        backend — "memory"（默认）| "graphdb"
    """

    def __init__(self, backend: str = _DEFAULT_BACKEND):
        self._backend = backend

    # ── 核心推理接口 ──────────────────────────────────────────────────────────

    def infer_single(
        self,
        user_id: str,
        force_refresh: bool = False,
    ):
        """
        对单个用户执行推理并返回 UserNeedResult。

        参数：
            user_id       — 用户 ID（OWL 实例 local name）
            force_refresh — True 时清除旧结果并重推；False 时若已有结果则直接返回

        返回：
            UserNeedResult
        """
        if self._backend == "graphdb":
            return self._infer_single_graphdb(user_id, force_refresh)
        return self._infer_single_memory(user_id, force_refresh)

    def infer_and_inject(self, event, backend: str | None = None):
        """
        注入行为事件并立即返回最新推理结果。

        参数：
            event   — UserBehaviorEvent 实例
            backend — 后端覆盖（默认使用 self._backend）

        返回：
            UserNeedResult
        """
        from ontology_engine.ingestion.event_injector import EventInjector
        backend = backend or self._backend
        injector = EventInjector(backend=backend, auto_re_infer=True)
        result = injector.inject(event)
        if result is None:
            # auto_re_infer=False 时回退
            return self.infer_single(event.user_id, force_refresh=True)
        return result

    # ── Memory 后端 ───────────────────────────────────────────────────────────

    def _infer_single_memory(self, user_id: str, force_refresh: bool):
        from ontology_engine.core.ontology_registry import get_onto
        from ontology_engine.query.user_need_query  import get_user_needs
        from ontology_engine.abox.need_singletons   import get_need
        from ontology_engine.rules.rule_registry    import create_default_registry

        onto = get_onto()
        user = onto.search_one(iri=f"*#{user_id}")
        if user is None:
            raise ValueError(f"用户 '{user_id}' 不存在于本体中，请先调用 load_abox()")

        # 缓存命中
        if not force_refresh and user.has_inferred_need:
            logger.debug("Memory 缓存命中：用户 %s，直接返回已有推理结果", user_id)
            return get_user_needs(user, backend="memory")

        # 清除并重推
        with onto:
            user.has_inferred_need.clear()

        rules = create_default_registry().get_ordered_rules()
        with onto:
            for rule in rules:
                triggered_keys = rule.evaluate(user)
                for key in triggered_keys:
                    need_instance = get_need(key)
                    if need_instance not in user.has_inferred_need:
                        user.has_inferred_need.append(need_instance)

        return get_user_needs(user, backend="memory")

    # ── GraphDB 后端 ──────────────────────────────────────────────────────────

    def _infer_single_graphdb(self, user_id: str, force_refresh: bool):
        from ontology_engine.core.graphdb_client  import get_graphdb
        from ontology_engine.rules.reasoner       import _build_user_proxy, _need_key_to_local, _NeedProxy
        from ontology_engine.rules.rule_registry  import create_default_registry
        from ontology_engine.query.user_need_query import get_user_needs

        client   = get_graphdb()
        ns       = ONTO_NS
        user_iri = f"{ns}{user_id}"

        # 缓存命中检查
        if not force_refresh:
            rows = client.sparql_select(f"""
                SELECT ?need WHERE {{
                    <{user_iri}> <{ns}has_inferred_need> ?need .
                }} LIMIT 1
            """)
            if rows:
                logger.debug("GraphDB 缓存命中：用户 %s，直接返回已有推理结果", user_id)
                return get_user_needs(user_id, backend="graphdb")

        # 清除旧结果
        client.sparql_update(f"""
            DELETE {{ <{user_iri}> <{ns}has_inferred_need> ?need }}
            WHERE  {{ <{user_iri}> <{ns}has_inferred_need> ?need }}
        """)

        # 执行规则
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
                for key in triggered_keys:
                    need_iri = f"{ns}{_need_key_to_local(key)}"
                    proxy.has_inferred_need.append(_NeedProxy(need_iri))

        return get_user_needs(user_id, backend="graphdb")
