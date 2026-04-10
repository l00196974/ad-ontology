"""
规则存储与发布门控
==================
提供人工审核接口：列出待审核规则、发布、拒绝。
"""
from __future__ import annotations

from neotrace.storage.base import StorageAdapter


class RuleStore:

    def __init__(self, storage: StorageAdapter):
        self._storage = storage

    def list_pending(self, rule_type: str | None = None) -> list[dict]:
        """列出所有待审核（draft）规则，可按类型过滤"""
        rules = self._storage.get_rules("draft")
        if rule_type:
            rules = [r for r in rules if r.get("rule_type") == rule_type]
        return rules

    def list_published(self, rule_type: str | None = None) -> list[dict]:
        """列出所有已发布规则"""
        rules = self._storage.get_rules("published")
        if rule_type:
            rules = [r for r in rules if r.get("rule_type") == rule_type]
        return rules

    def publish(self, rule_id: str) -> None:
        """发布规则（draft → published）"""
        self._storage.update_rule_status(rule_id, "published")
        print(f"[RuleStore] 规则 {rule_id} 已发布")

    def reject(self, rule_id: str) -> None:
        """拒绝规则（draft → rejected）"""
        self._storage.update_rule_status(rule_id, "rejected")
        print(f"[RuleStore] 规则 {rule_id} 已拒绝")

    def publish_all_cep(self, min_tgi: float = 100.0) -> int:
        """批量发布 TGI 达标的 CEP 规则（自动模式）"""
        rules = self._storage.get_rules("draft")
        count = 0
        for r in rules:
            if r.get("rule_type") == "cep_clean" and (r.get("tgi") or 0) >= min_tgi:
                self.publish(r["rule_id"])
                count += 1
        return count

    def publish_all_need(self, min_tgi: float = 120.0) -> int:
        """批量发布 TGI 达标的 NEED 规则（自动模式）"""
        rules = self._storage.get_rules("draft")
        count = 0
        for r in rules:
            if r.get("rule_type") == "need_segment" and (r.get("tgi") or 0) >= min_tgi:
                self.publish(r["rule_id"])
                count += 1
        return count

    def print_report(self) -> None:
        """打印规则审核报告"""
        for status in ["draft", "published", "rejected"]:
            rules = self._storage.get_rules(status)
            if not rules:
                continue
            print(f"\n{'='*60}")
            print(f"  {status.upper()} 规则 ({len(rules)} 条)")
            print(f"{'='*60}")
            for r in rules:
                print(f"  [{r.get('rule_type','?')}] {r.get('name','?')}")
                print(f"    TGI={r.get('tgi') or 0:.1f}  "
                      f"覆盖={r.get('support') or 0:.1%}  "
                      f"命中={r.get('hit_users') or 0:,}人")
                print(f"    说明: {r.get('description','')[:80]}")
