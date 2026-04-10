"""
策略引擎
========
输入: item_name + budget → 输出: 完整投放策略建议

核心逻辑：
  1. 从本体查询 Item 属性 → 确定相关 NEED 及权重向量
  2. 从 need_tags 表读取用户 NEED 标签（Spark 打标或本地推理产出）
  3. 计算用户综合意向分（全局调权：不同 Item 下权重不同）
  4. 在预算约束下从高到低取 TopK 用户
  5. 匹配媒体（从外部接入 or 规则回退）+ 素材
  6. 输出 StrategyResult
"""
from __future__ import annotations

from dataclasses import dataclass, field

from neotrace.storage.base import StorageAdapter
try:
    from neotrace.ontology.registry import get_onto
except ImportError:
    def get_onto(): return None  # type: ignore


@dataclass
class PlacementRec:
    platform: str
    ad_format: str
    buying_type: str
    budget_allocated: float
    estimated_reach: int
    reason: str


@dataclass
class CreativeRec:
    creative_id: str
    theme: str
    key_message: str
    serves_need: str


@dataclass
class StrategyResult:
    item_name: str
    total_budget: float
    total_users: int
    intent_score_p90: float
    intent_score_p50: float
    need_distribution: dict[str, int]          # {need_label: user_count}
    placements: list[PlacementRec]
    creatives: list[CreativeRec]
    estimated_reach: int
    estimated_conversions: int
    avg_tgi: float
    summary: str


class StrategyEngine:

    # 每用户预估曝光成本（元），无外部数据时使用默认值
    DEFAULT_CPM = 25.0
    DEFAULT_FREQ = 3.0    # 人均曝光频次

    def __init__(self, storage: StorageAdapter):
        self._storage = storage
        self._onto = get_onto()

    def query(self, item_name: str, budget: float, objective: str = "conversions") -> StrategyResult:
        """
        生成投放策略。

        Args:
            item_name: 产品名称，如 "问界M7"
            budget:    总预算（元）
            objective: 优化目标（conversions/reach/clicks）
        """
        print(f"\n[StrategyEngine] 查询策略: {item_name}, 预算={budget/10000:.0f}万")

        # 1. 获取 Item 属性 → NEED 权重向量
        need_weights = self._get_need_weights(item_name)
        print(f"  NEED 权重向量: {need_weights}")

        # 2. 读取用户 NEED 标签
        need_tags = self._storage.query(
            "SELECT user_id, need_label, confidence FROM need_tags"
        )
        if not need_tags:
            print("  [警告] need_tags 表为空，请先运行本地推理或 Spark 打标")
            return self._empty_result(item_name, budget)

        # 3. 计算综合意向分（全局调权融合）
        user_scores = self._compute_intent_scores(need_tags, need_weights)
        print(f"  参与意向评分用户数: {len(user_scores):,}")

        # 4. 预算约束 TopK 用户
        cost_per_user = self.DEFAULT_CPM * self.DEFAULT_FREQ / 1000
        k = min(int(budget / cost_per_user), len(user_scores))
        sorted_users = sorted(user_scores.items(), key=lambda x: x[1], reverse=True)
        topk_users = sorted_users[:k]

        # 意向分分布
        scores = [s for _, s in topk_users]
        p90 = scores[int(len(scores) * 0.1)] if scores else 0
        p50 = scores[int(len(scores) * 0.5)] if scores else 0

        # 5. NEED 分布统计
        need_dist = self._compute_need_distribution(
            [uid for uid, _ in topk_users], need_tags
        )

        # 6. 媒体推荐（规则回退）
        placements = self._recommend_placements(need_dist, budget)

        # 7. 素材推荐
        creatives = self._recommend_creatives(need_dist, item_name)

        # 8. 效果预估
        avg_tgi = self._get_avg_tgi_for_needs(list(need_dist.keys()))
        global_cvr = self._storage.get_conversion_rate()
        estimated_cvr = global_cvr * (avg_tgi / 100)
        estimated_conversions = int(k * estimated_cvr)

        summary = self._build_summary(
            item_name, budget, k, need_dist, placements, estimated_conversions, avg_tgi
        )

        return StrategyResult(
            item_name=item_name,
            total_budget=budget,
            total_users=k,
            intent_score_p90=round(p90, 3),
            intent_score_p50=round(p50, 3),
            need_distribution=need_dist,
            placements=placements,
            creatives=creatives,
            estimated_reach=k,
            estimated_conversions=estimated_conversions,
            avg_tgi=avg_tgi,
            summary=summary,
        )

    def _get_need_weights(self, item_name: str) -> dict[str, float]:
        """
        基于 Item 属性推导 NEED 权重向量。
        当前实现：从本体查询 CarModel 属性，按业务规则赋权。
        后续可替换为 LLM 动态生成。
        """
        onto = self._onto
        weights: dict[str, float] = {}

        # 尝试从本体查找 CarModel 实例
        car = None
        if onto is not None and hasattr(onto, "CarModel"):
            for inst in onto.CarModel.instances():
                if inst.name == item_name:
                    car = inst
                    break

        if car is None:
            # 默认权重（兜底）
            return {
                "SpaceNeed": 0.3,
                "BudgetSensitivity": 0.3,
                "LicensePlateUrgency": 0.2,
                "RangeMileageAnxiety": 0.1,
                "CommuteNeed": 0.1,
            }

        # 基于车型属性动态赋权
        seat = getattr(car, "seat_layout", "") or ""
        power = getattr(car, "power_type", "") or ""
        price = getattr(car, "msrp", 0) or 0

        if "6" in seat or "7" in seat:
            weights["SpaceNeed"] = 0.5
        else:
            weights["SpaceNeed"] = 0.15

        if "增程" in power or "插混" in power:
            weights["RangeMileageAnxiety"] = 0.25
            weights["LicensePlateUrgency"] = 0.2
        elif "纯电" in power:
            weights["LicensePlateUrgency"] = 0.3
            weights["RangeMileageAnxiety"] = 0.05

        if price >= 30:
            weights["BudgetSensitivity"] = 0.15
        else:
            weights["BudgetSensitivity"] = 0.3

        weights.setdefault("CommuteNeed", 0.1)
        weights.setdefault("SpaceNeed", 0.2)
        weights.setdefault("LicensePlateUrgency", 0.15)
        weights.setdefault("RangeMileageAnxiety", 0.1)
        weights.setdefault("BudgetSensitivity", 0.2)

        # 归一化
        total = sum(weights.values())
        return {k: round(v / total, 3) for k, v in weights.items()}

    def _compute_intent_scores(
        self,
        need_tags: list[dict],
        weights: dict[str, float],
    ) -> dict[str, float]:
        """
        全局调权融合：
        score(user) = Σ [w_need × confidence(user, need)]
        """
        scores: dict[str, float] = {}
        for row in need_tags:
            uid = row["user_id"]
            need = row["need_label"]
            conf = float(row.get("confidence") or 1.0)
            w = weights.get(need, 0.0)
            scores[uid] = scores.get(uid, 0.0) + w * conf
        return scores

    def _compute_need_distribution(
        self,
        topk_user_ids: list[str],
        need_tags: list[dict],
    ) -> dict[str, int]:
        uid_set = set(topk_user_ids)
        dist: dict[str, int] = {}
        for row in need_tags:
            if row["user_id"] in uid_set:
                need = row["need_label"]
                dist[need] = dist.get(need, 0) + 1
        return dict(sorted(dist.items(), key=lambda x: x[1], reverse=True))

    def _recommend_placements(
        self,
        need_dist: dict[str, int],
        budget: float,
    ) -> list[PlacementRec]:
        """
        媒体推荐（规则回退，外部系统未接入时使用）。
        TODO: 接入 MediaPerformanceAdapter 后替换为数据驱动。
        """
        # 简单规则：按 NEED 分布决定媒体组合
        dominant_need = list(need_dist.keys())[0] if need_dist else "SpaceNeed"

        media_rules = {
            "SpaceNeed":           [("抖音", "信息流", "RTB竞价", 0.4),
                                    ("华为广告", "信息流", "RTB竞价", 0.35),
                                    ("微信", "朋友圈", "GD合约", 0.25)],
            "BudgetSensitivity":   [("微信", "搜索", "CPC", 0.5),
                                    ("华为广告", "搜索", "CPC", 0.3),
                                    ("抖音", "信息流", "RTB竞价", 0.2)],
            "LicensePlateUrgency": [("华为广告", "信息流", "RTB竞价", 0.45),
                                    ("抖音", "开屏", "GD合约", 0.3),
                                    ("小红书", "信息流", "RTB竞价", 0.25)],
            "RangeMileageAnxiety": [("抖音", "贴片", "CPCV", 0.5),
                                    ("华为广告", "信息流", "RTB竞价", 0.3),
                                    ("微信", "公众号", "GD合约", 0.2)],
            "CommuteNeed":         [("华为广告", "信息流", "RTB竞价", 0.5),
                                    ("抖音", "信息流", "RTB竞价", 0.3),
                                    ("微信", "朋友圈", "GD合约", 0.2)],
        }
        media_mix = media_rules.get(dominant_need, media_rules["SpaceNeed"])
        cost_per_user = self.DEFAULT_CPM * self.DEFAULT_FREQ / 1000

        return [
            PlacementRec(
                platform=m[0],
                ad_format=m[1],
                buying_type=m[2],
                budget_allocated=round(budget * m[3]),
                estimated_reach=int(budget * m[3] / cost_per_user),
                reason=f"主导 NEED 为 {dominant_need}",
            )
            for m in media_mix
        ]

    def _recommend_creatives(
        self,
        need_dist: dict[str, int],
        item_name: str,
    ) -> list[CreativeRec]:
        """从本体查找与主导 NEED 匹配的素材"""
        onto = self._onto
        recs = []
        if onto is None or not hasattr(onto, "Creative"):
            return recs

        dominant_needs = list(need_dist.keys())[:2]
        need_theme_map = {
            "SpaceNeed":           "空间",
            "BudgetSensitivity":   "性价比",
            "LicensePlateUrgency": "科技",
            "RangeMileageAnxiety": "增程",
            "CommuteNeed":         "通勤",
        }
        target_themes = [need_theme_map.get(n, "") for n in dominant_needs]

        for inst in onto.Creative.instances():
            theme = getattr(inst, "theme", "") or ""
            if any(t and t in theme for t in target_themes):
                recs.append(CreativeRec(
                    creative_id=getattr(inst, "creative_id", inst.name),
                    theme=theme,
                    key_message=getattr(inst, "key_message", ""),
                    serves_need=dominant_needs[0] if dominant_needs else "",
                ))
        return recs[:3]

    def _get_avg_tgi_for_needs(self, need_labels: list[str]) -> float:
        if not need_labels:
            return 100.0
        rules = self._storage.get_rules("published")
        tgis = [
            float(r.get("tgi") or 100)
            for r in rules
            if r.get("need_label") in need_labels and r.get("rule_type") == "need_segment"
        ]
        return round(sum(tgis) / len(tgis), 1) if tgis else 100.0

    def _empty_result(self, item_name: str, budget: float) -> StrategyResult:
        return StrategyResult(
            item_name=item_name, total_budget=budget, total_users=0,
            intent_score_p90=0, intent_score_p50=0, need_distribution={},
            placements=[], creatives=[], estimated_reach=0,
            estimated_conversions=0, avg_tgi=0,
            summary="暂无打标数据，请先运行离线 Pipeline。",
        )

    def _build_summary(
        self,
        item_name: str,
        budget: float,
        k: int,
        need_dist: dict,
        placements: list,
        conversions: int,
        avg_tgi: float,
    ) -> str:
        need_str = "、".join(
            f"{n}({c:,}人)" for n, c in list(need_dist.items())[:3]
        )
        media_str = "、".join(f"{p.platform}({p.ad_format})" for p in placements[:2])
        return (
            f"建议将 {budget/10000:.0f}万 预算投放给 {k:,} 位高意向用户，"
            f"主要覆盖 {need_str} 等需求人群，"
            f"推荐媒体：{media_str}，"
            f"参考平均 TGI={avg_tgi:.0f}，"
            f"预估转化 {conversions:,} 人。"
        )
