"""
购车链路匹配器
==============
给定用户已触发的事件集合，计算该用户与各典型链路的匹配得分，
返回最佳匹配链路及其置信度。

匹配算法：
  对每条链路，计算用户事件覆盖率（覆盖节点数 / 链路节点总数）
  × 沿路径的联合概率（各节点条件概率之积）
  = 最终匹配得分

当前实现为基于规则的启发式匹配，可替换为概率图模型或 GNN。
"""

from dataclasses import dataclass
from ontology_engine.journey.purchase_journeys import PURCHASE_JOURNEYS, PurchaseJourney


@dataclass
class JourneyMatchResult:
    """链路匹配结果"""
    journey_id:       str
    journey_name:     str
    match_score:      float     # 0-1，越高越匹配
    coverage:         float     # 事件覆盖率
    matched_events:   list[str] # 用户已触发的链路节点事件 ID
    missing_events:   list[str] # 链路中尚未触发的事件 ID（营销介入机会点）
    target_persona:   str
    recommended_cars: list[str]


class JourneyMatcher:
    """购车链路匹配器"""

    def match(self, triggered_event_ids: set[str]) -> list[JourneyMatchResult]:
        """
        匹配所有链路并排序返回。

        参数：
            triggered_event_ids: 用户已触发的事件 ID 集合（如 {"E003", "E101", "E102"}）

        返回：
            按 match_score 降序排列的匹配结果列表
        """
        results = []

        for journey in PURCHASE_JOURNEYS:
            node_event_ids = [node.event_id for node in journey.nodes]
            matched   = [eid for eid in node_event_ids if eid in triggered_event_ids]
            missing   = [eid for eid in node_event_ids if eid not in triggered_event_ids]

            coverage = len(matched) / len(node_event_ids) if node_event_ids else 0.0

            # 计算路径联合概率（只计算已匹配节点前的路径片段）
            path_prob = 1.0
            for node in journey.nodes:
                if node.event_id in triggered_event_ids:
                    path_prob *= node.probability
                else:
                    break  # 链路中断，停止累乘

            match_score = round(coverage * path_prob, 4)

            if match_score > 0:
                results.append(JourneyMatchResult(
                    journey_id       = journey.journey_id,
                    journey_name     = journey.journey_name,
                    match_score      = match_score,
                    coverage         = round(coverage, 4),
                    matched_events   = matched,
                    missing_events   = missing,
                    target_persona   = journey.target_persona,
                    recommended_cars = list(journey.recommended_cars),
                ))

        return sorted(results, key=lambda r: r.match_score, reverse=True)

    def best_match(self, triggered_event_ids: set[str]) -> JourneyMatchResult | None:
        """返回得分最高的匹配链路，若无匹配返回 None"""
        results = self.match(triggered_event_ids)
        return results[0] if results else None
