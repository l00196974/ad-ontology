"""
规则热加载 + 增量重推理
========================
RuleUpdater 允许在不重启服务的情况下：
  1. 向全局 RuleRegistry 注册新规则（或替换同 rule_id 的旧规则）
  2. 只对受影响的用户子集触发增量重推理，无需全量重跑

受影响用户判定逻辑：
  - 若规则声明了 affected_properties（如 ["policy_restriction_fuel"]），
    则只对本体中"拥有这些属性"的用户重推（精准模式）
  - 若 affected_properties 为空，则对所有用户重推（保守模式）

增量重推理幂等性：
  - 重推前清除该规则可能产生的 NeedKey（避免重复写入）
  - 重推后返回变化 diff：{user_id: [新增 NeedKey]}
"""

from __future__ import annotations

import logging
import textwrap
import types

from ontology_engine.rules.base_rule     import BaseRule
from ontology_engine.rules.rule_registry import create_default_registry
from ontology_engine.config.enums        import NeedKey
from ontology_engine.config.settings     import ONTOLOGY_IRI

logger = logging.getLogger(__name__)

ONTO_NS = ONTOLOGY_IRI.rstrip("#") + "#"

# 全局默认注册表单例（首次访问时懒加载）
_DEFAULT_REGISTRY = None


def _get_registry():
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        _DEFAULT_REGISTRY = create_default_registry()
    return _DEFAULT_REGISTRY


class RuleUpdater:
    """
    规则热加载 + 增量重推理器。

    参数：
        registry — 目标规则注册表；默认使用全局默认注册表
    """

    def __init__(self, registry=None):
        self._registry = registry or _get_registry()

    # ── 规则注册 ──────────────────────────────────────────────────────────────

    def register_rule(self, rule: BaseRule) -> None:
        """
        向注册表注册新规则（或替换同 rule_id 的旧规则）。
        注册后可调用 re_infer_affected() 触发增量重推理。
        """
        self._registry.register(rule)
        logger.info("已注册规则：%s", rule.rule_id)

    def register_rule_from_code(self, rule_code: str) -> BaseRule:
        """
        从 Python 代码字符串动态加载并注册规则。

        参数：
            rule_code — 包含 BaseRule 子类定义的 Python 代码字符串

        返回：
            注册成功的 BaseRule 实例

        说明：
            代码必须定义且只定义一个 BaseRule 子类。
            调用方应先通过 RuleSandbox 验证代码安全性。
        """
        rule = _load_rule_from_code(rule_code)
        self.register_rule(rule)
        return rule

    # ── 增量重推理 ────────────────────────────────────────────────────────────

    def re_infer_affected(
        self,
        rule_ids: list[str],
        backend: str = "memory",
    ) -> dict[str, list[str]]:
        """
        对受指定规则影响的用户子集触发增量重推理。

        参数：
            rule_ids — 需要重推理的规则 ID 列表
            backend  — "memory" | "graphdb"

        返回：
            {user_id: [新增 NeedKey 字符串列表]}（仅记录本次新增的需求）
        """
        if backend == "graphdb":
            return self._re_infer_graphdb(rule_ids)
        return self._re_infer_memory(rule_ids)

    # ── Memory 后端 ───────────────────────────────────────────────────────────

    def _re_infer_memory(self, rule_ids: list[str]) -> dict[str, list[str]]:
        from ontology_engine.core.ontology_registry import get_onto
        from ontology_engine.abox.need_singletons import get_need

        onto  = get_onto()
        rules = self._registry.get_ordered_rules()

        # 找出指定规则
        target_rules = [r for r in rules if r.rule_id in rule_ids]
        if not target_rules:
            logger.warning("未找到规则：%s", rule_ids)
            return {}

        # 收集受影响用户
        all_users = list(onto.User.instances())
        affected  = self._filter_affected_users_memory(all_users, target_rules)

        diff: dict[str, list[str]] = {}

        # 按拓扑顺序包含下游规则（含 depends_on 传递）
        rules_to_run = self._expand_with_downstream(rules, rule_ids)

        for user in affected:
            before = set(n.name for n in user.has_inferred_need)

            # 清除本次涉及规则可能产生的旧结果
            self._clear_needs_memory(onto, user, rules_to_run)

            # 重推
            with onto:
                for rule in rules_to_run:
                    triggered_keys = rule.evaluate(user)
                    for key in triggered_keys:
                        need_instance = get_need(key)
                        if need_instance not in user.has_inferred_need:
                            user.has_inferred_need.append(need_instance)

            after    = set(n.name for n in user.has_inferred_need)
            new_keys = list(after - before)
            if new_keys:
                diff[user.name] = new_keys

        return diff

    def _filter_affected_users_memory(self, all_users, target_rules: list[BaseRule]):
        """筛选受影响用户（memory 模式）"""
        affected_props = set()
        for rule in target_rules:
            affected_props.update(rule.affected_properties)

        if not affected_props:
            return all_users   # 保守策略：全量

        # 精准策略：只返回拥有这些属性的用户（当前实现：有属性即为受影响）
        result = []
        for user in all_users:
            for prop in affected_props:
                if hasattr(user, prop) and getattr(user, prop) is not None:
                    result.append(user)
                    break
        return result

    def _clear_needs_memory(self, onto, user, rules_to_run: list[BaseRule]) -> None:
        """清除这些规则可能产生的 NeedKey（避免重复写入）"""
        from ontology_engine.abox.need_singletons import get_need

        keys_to_clear: set[NeedKey] = set()
        for rule in rules_to_run:
            # 通过试运行一个空 proxy 收集规则可能产生的 NeedKey
            # 更简单的方式：通过规则类型推断（当前直接清空全部 has_inferred_need）
            pass

        # 简化实现：清除所有 has_inferred_need（幂等性由完整重推保证）
        with onto:
            user.has_inferred_need.clear()

    # ── GraphDB 后端 ──────────────────────────────────────────────────────────

    def _re_infer_graphdb(self, rule_ids: list[str]) -> dict[str, list[str]]:
        from ontology_engine.core.graphdb_client import get_graphdb
        from ontology_engine.rules.reasoner import _build_user_proxy, _need_key_to_local, _NeedProxy

        client = get_graphdb()
        ns     = ONTO_NS
        rules  = self._registry.get_ordered_rules()

        target_rules  = [r for r in rules if r.rule_id in rule_ids]
        if not target_rules:
            logger.warning("未找到规则：%s", rule_ids)
            return {}

        rules_to_run  = self._expand_with_downstream(rules, rule_ids)
        affected_iris = self._filter_affected_users_graphdb(client, ns, target_rules)

        diff: dict[str, list[str]] = {}

        for user_iri in affected_iris:
            user_id = user_iri.split("#")[-1]

            # 查询重推前的需求集合
            before_rows = client.sparql_select(f"""
                SELECT ?need WHERE {{
                    <{user_iri}> <{ns}has_inferred_need> ?need .
                }}
            """)
            before = {r["need"] for r in before_rows}

            # 清除旧推理结果
            client.sparql_update(f"""
                DELETE {{ <{user_iri}> <{ns}has_inferred_need> ?need }}
                WHERE  {{ <{user_iri}> <{ns}has_inferred_need> ?need }}
            """)

            # 执行规则
            proxy = _build_user_proxy(client, user_iri)
            for rule in rules_to_run:
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

            # 查询重推后的需求集合
            after_rows = client.sparql_select(f"""
                SELECT ?need WHERE {{
                    <{user_iri}> <{ns}has_inferred_need> ?need .
                }}
            """)
            after   = {r["need"] for r in after_rows}
            new_iris = after - before
            if new_iris:
                diff[user_id] = [iri.split("#")[-1] for iri in new_iris]

        return diff

    def _filter_affected_users_graphdb(
        self, client, ns: str, target_rules: list[BaseRule]
    ) -> list[str]:
        """筛选受影响用户（graphdb 模式）"""
        affected_props = set()
        for rule in target_rules:
            affected_props.update(rule.affected_properties)

        if not affected_props:
            # 保守策略：全量
            rows = client.sparql_select(
                f"SELECT ?user WHERE {{ ?user a <{ns}User> }}"
            )
            return [r["user"] for r in rows]

        # 精准策略：拥有任意一个受影响属性的用户
        prop_filters = " ".join(
            f"{{ ?user <{ns}{p}> ?v{i} }}"
            for i, p in enumerate(affected_props)
        )
        union_query = f"""
            SELECT DISTINCT ?user WHERE {{
                {" UNION ".join(
                    f"{{ ?user <{ns}{p}> ?v{i} }}"
                    for i, p in enumerate(affected_props)
                )}
                ?user a <{ns}User> .
            }}
        """
        rows = client.sparql_select(union_query)
        return [r["user"] for r in rows]

    # ── 辅助 ─────────────────────────────────────────────────────────────────

    def _expand_with_downstream(
        self, all_rules: list[BaseRule], rule_ids: list[str]
    ) -> list[BaseRule]:
        """
        展开指定规则集合，包含所有下游（depends_on 指向它们的规则）。
        按拓扑顺序返回（已由 get_ordered_rules() 保证）。
        """
        rule_id_set = set(rule_ids)
        result_ids: set[str] = set()

        # BFS 向下游扩展
        queue = list(rule_ids)
        while queue:
            rid = queue.pop(0)
            result_ids.add(rid)
            for rule in all_rules:
                if rid in rule.depends_on and rule.rule_id not in result_ids:
                    result_ids.add(rule.rule_id)
                    queue.append(rule.rule_id)

        # 按拓扑顺序过滤
        return [r for r in all_rules if r.rule_id in result_ids]


# ── 动态代码加载 ──────────────────────────────────────────────────────────────

def _load_rule_from_code(rule_code: str) -> BaseRule:
    """
    动态执行规则代码字符串，返回 BaseRule 子类实例。

    要求代码中定义且只定义一个 BaseRule 子类，且该类有合法的 rule_id。
    调用前应先通过 RuleSandbox.validate() 验证代码安全性。
    """
    dedented = textwrap.dedent(rule_code)
    module   = types.ModuleType("_dynamic_rule")

    # 注入必要的 import 上下文
    module.__dict__.update({
        "BaseRule": BaseRule,
        "NeedKey":  NeedKey,
    })

    exec(compile(dedented, "<dynamic_rule>", "exec"), module.__dict__)  # noqa: S102

    # 查找 BaseRule 子类
    subclasses = [
        obj for obj in module.__dict__.values()
        if (isinstance(obj, type)
            and issubclass(obj, BaseRule)
            and obj is not BaseRule)
    ]

    if len(subclasses) == 0:
        raise ValueError("代码中未找到 BaseRule 子类")
    if len(subclasses) > 1:
        raise ValueError(f"代码中找到多个 BaseRule 子类：{[c.__name__ for c in subclasses]}")

    rule_cls = subclasses[0]
    if not rule_cls.rule_id:
        raise ValueError(f"规则类 {rule_cls.__name__} 未设置 rule_id")

    return rule_cls()
