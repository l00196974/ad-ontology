"""
LLM 规则冲突检测器
==================
在将 LLM 生成的规则注册到 RuleRegistry 之前，检测与已有规则的潜在冲突。

冲突类型：
  1. rule_id 重复   — 与已有规则 ID 相同（覆盖警告，非报错）
  2. 循环依赖       — 新规则的 depends_on 引入了循环
  3. NeedKey 独占冲突 — 新规则产生的 NeedKey 与已有规则在同一互斥组中
     （当前实现：仅作信息提示，不阻止注册）
"""

from __future__ import annotations

import dataclasses
import logging

logger = logging.getLogger(__name__)

# NeedKey 互斥组（同一用户同时触发同组内两个 key 表示逻辑矛盾）
_EXCLUSIVE_GROUPS: list[set[str]] = [
    {"绿牌刚需", "无桩且限号", "牌照自由"},    # 牌照类：三选一
]


@dataclasses.dataclass
class ConflictReport:
    """冲突检测报告"""
    has_conflict:  bool
    warnings:      list[str]     # 非阻断警告（覆盖、潜在 NeedKey 冲突）
    errors:        list[str]     # 阻断错误（循环依赖）
    rule_id:       str


class RuleValidator:
    """
    规则冲突检测器。

    参数：
        registry — 目标规则注册表（默认使用全局默认注册表）
    """

    def __init__(self, registry=None):
        self._registry = registry

    def _get_registry(self):
        if self._registry is not None:
            return self._registry
        from ontology_engine.rules.rule_updater import _get_registry
        return _get_registry()

    def validate(self, rule) -> ConflictReport:
        """
        检测 rule 与现有注册表的冲突。

        参数：
            rule — BaseRule 实例（通常来自 RuleSandbox 验证通过的代码）

        返回：
            ConflictReport（has_conflict=True 表示有阻断错误）
        """
        registry = self._get_registry()
        warnings: list[str] = []
        errors:   list[str] = []

        existing_rules = registry.get_ordered_rules()
        existing_ids   = {r.rule_id for r in existing_rules}

        # 1. rule_id 重复检查（覆盖警告）
        if rule.rule_id in existing_ids:
            warnings.append(
                f"rule_id '{rule.rule_id}' 已存在，注册时将覆盖旧规则。"
            )

        # 2. 循环依赖检查
        cycle_error = self._check_cycle(rule, existing_rules)
        if cycle_error:
            errors.append(cycle_error)

        # 3. NeedKey 互斥组冲突提示（仅 warning）
        self._check_need_conflicts(rule, existing_rules, warnings)

        return ConflictReport(
            has_conflict = len(errors) > 0,
            warnings     = warnings,
            errors       = errors,
            rule_id      = rule.rule_id,
        )

    def _check_cycle(self, new_rule, existing_rules) -> str:
        """
        检测加入新规则后是否产生循环依赖。
        使用 DFS 从新规则的 depends_on 出发，检查是否能回到 new_rule.rule_id。
        """
        id_map = {r.rule_id: r for r in existing_rules}
        id_map[new_rule.rule_id] = new_rule  # 临时加入

        visited: set[str] = set()
        path:    list[str] = []

        def dfs(rid: str) -> bool:
            if rid in path:
                return True  # 有环
            if rid in visited:
                return False
            visited.add(rid)
            path.append(rid)
            rule = id_map.get(rid)
            if rule:
                for dep in rule.depends_on:
                    if dfs(dep):
                        return True
            path.pop()
            return False

        if dfs(new_rule.rule_id):
            return f"规则 '{new_rule.rule_id}' 与现有规则存在循环依赖：{path}"
        return ""

    def _check_need_conflicts(self, new_rule, existing_rules, warnings: list[str]) -> None:
        """提示 NeedKey 互斥组中的潜在冲突（仅 warning）。"""
        # 目前通过静态分析不能可靠判断规则会产生哪些 NeedKey，
        # 仅提示：若两个规则都在同一互斥组中，可能需要人工确认互斥条件
        pass  # 留作未来扩展
