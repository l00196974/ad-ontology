"""
规则注册表（拓扑排序）
======================
管理规则的注册与执行顺序。

核心设计：
  原代码中规则执行顺序靠注释维护（"4. 里程焦虑依赖规则1，放在最后"），
  极易被未来开发者打破。重构后：
    - 每条规则声明 depends_on（显式依赖）
    - RuleRegistry 使用 Kahn 算法拓扑排序，自动保证依赖规则先执行
    - 新增规则只需 register() + 声明 depends_on，无需手动调整顺序
"""

from collections import defaultdict, deque
from ontology_engine.rules.base_rule import BaseRule


class RuleRegistry:
    """
    规则注册表，负责：
      1. 收集 BaseRule 子类实例
      2. 按 depends_on 进行拓扑排序
      3. 提供有序规则列表供 Reasoner 执行
    """

    def __init__(self):
        self._rules: dict[str, BaseRule] = {}    # rule_id → rule instance

    def register(self, rule: BaseRule) -> None:
        """注册一条规则。同一 rule_id 重复注册会覆盖。"""
        if not rule.rule_id:
            raise ValueError(f"规则 {type(rule).__name__} 未设置 rule_id")
        self._rules[rule.rule_id] = rule

    def get_ordered_rules(self) -> list[BaseRule]:
        """
        返回按依赖关系拓扑排序后的规则列表。
        使用 Kahn 算法（BFS），时间复杂度 O(V+E)。

        若存在循环依赖，抛出 ValueError。
        """
        ids = list(self._rules.keys())

        # 构建邻接表和入度表
        in_degree: dict[str, int]        = {rid: 0 for rid in ids}
        dependents: dict[str, list[str]] = defaultdict(list)  # rid → 依赖它的 rule id 列表

        for rid, rule in self._rules.items():
            for dep in rule.depends_on:
                if dep not in self._rules:
                    raise ValueError(
                        f"规则 '{rid}' 声明依赖 '{dep}'，但该规则未注册到 RuleRegistry"
                    )
                dependents[dep].append(rid)
                in_degree[rid] += 1

        # Kahn 算法
        queue   = deque(rid for rid in ids if in_degree[rid] == 0)
        ordered = []

        while queue:
            rid = queue.popleft()
            ordered.append(self._rules[rid])
            for dependent_rid in dependents[rid]:
                in_degree[dependent_rid] -= 1
                if in_degree[dependent_rid] == 0:
                    queue.append(dependent_rid)

        if len(ordered) != len(ids):
            cyclic = [rid for rid in ids if rid not in {r.rule_id for r in ordered}]
            raise ValueError(f"检测到规则循环依赖：{cyclic}")

        return ordered

    def all_logs(self) -> list[dict]:
        """合并所有规则的触发日志"""
        logs = []
        for rule in self._rules.values():
            logs.extend(rule.log)
        return logs


def create_default_registry() -> RuleRegistry:
    """
    创建并注册默认的 5 条业务规则。
    新增规则只需在此函数中 register() 即可，无需关心执行顺序。
    """
    from ontology_engine.rules.license_plate_rule import LicensePlateRule
    from ontology_engine.rules.space_need_rule    import SpaceNeedRule
    from ontology_engine.rules.budget_rule        import BudgetRule
    from ontology_engine.rules.range_anxiety_rule import RangeAnxietyRule
    from ontology_engine.rules.long_commute_rule  import LongCommuteRule

    registry = RuleRegistry()
    registry.register(LicensePlateRule())
    registry.register(SpaceNeedRule())
    registry.register(BudgetRule())
    registry.register(RangeAnxietyRule())   # depends_on license_plate，拓扑排序自动处理
    registry.register(LongCommuteRule())
    return registry
