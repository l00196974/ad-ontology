"""
策略引擎（扁平化版）
====================
输入: item_name + budget + target_audience_size → 输出: 完整投放策略建议

用户意向评分公式：
  score(user) = Σ [need_weight(need_i) × tgi_normalized(rule_j)] for 每条命中规则 rule_j ∈ need_i
  其中 tgi_normalized = rule.tgi / 100（TGI=100 为基准，>100 表示高于均值）

TopK 后按主导需求分组：
  每个用户的主导需求 = 得分最高的那个需求
  按主导需求分组，每组独立推荐媒体/素材/预算
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from collections import defaultdict

from neotrace.storage.base import StorageAdapter
from neotrace.llm_client import llm_stream_call

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
class NeedGroup:
    """按主导需求划分的用户分组"""
    need_label: str           # 需求标签（中文）
    need_weight: float        # 该需求在本 Item 下的权重
    user_count: int           # 分组用户数
    budget_allocated: float   # 分配预算
    avg_score: float          # 组内用户平均意向分
    placements: list[PlacementRec]
    creatives: list[CreativeRec]


@dataclass
class StrategyResult:
    item_name: str
    total_budget: float
    total_users: int
    target_audience_size: int         # 用户传入的目标投放人群数（0 表示由预算决定）
    intent_score_p90: float
    intent_score_p50: float
    matched_rules: list[str]
    inferred_needs: list[str]
    need_groups: list[NeedGroup]      # 按主导需求分组的投放策略
    placements: list[PlacementRec]    # 全局推荐（不分组时使用）
    creatives: list[CreativeRec]
    estimated_reach: int
    estimated_conversions: int
    avg_tgi: float
    summary: str


class StrategyEngine:

    DEFAULT_CPM = 25.0   # 每千次曝光成本（元）
    DEFAULT_FREQ = 3.0   # 人均曝光频次

    def __init__(self, storage: StorageAdapter):
        self._storage = storage
        self._onto = get_onto()

    def query(
        self,
        item_name: str,
        budget: float,
        target_audience_size: int = 0,
        objective: str = "conversions",
    ) -> StrategyResult:
        """
        生成投放策略。

        Args:
            item_name:            产品名称，如 "问界M7"
            budget:               总预算（元）
            target_audience_size: 目标投放人群数量（0 表示由预算自动推算）
            objective:            优化目标（conversions/reach/clicks）
        """
        print(f"\n[StrategyEngine] 查询策略: {item_name}"
              f"  预算={budget/10000:.0f}万"
              f"  目标人群={'由预算决定' if not target_audience_size else f'{target_audience_size:,}人'}")

        # 1. 获取 Item 属性
        item_attrs = self._get_item_attrs(item_name)

        # 2. LLM 推断需求权重 + 每条规则归属需求
        print("  [LLM] 推断目标人群需求权重...")
        targeting = self._llm_infer_targeting(item_name, item_attrs)
        inferred_needs = [n["label"] for n in targeting.get("needs", [])]
        need_weights: dict[str, float] = {
            n["label"]: n["weight"] for n in targeting.get("needs", [])
        }
        rule_need_map: dict[str, str] = targeting.get("rule_need_map", {})  # 规则名 → 需求标签
        print(f"  推导需求: {[(n, f'{w:.2f}') for n, w in need_weights.items()]}")

        # 3. 已发布 CEP 规则
        published_rules = self._storage.get_rules("published")
        cep_rules = [r for r in published_rules if r.get("rule_type") == "cep_clean"]
        print(f"  已发布 CEP 规则: {len(cep_rules)} 条")

        if not cep_rules:
            print("  [警告] 无已发布 CEP 规则，请先运行离线 Pipeline")
            return self._empty_result(item_name, budget, target_audience_size, inferred_needs)

        # 4. 计算每个用户在每个需求上的得分
        #    user_need_scores[user_id][need_label] = score
        user_need_scores = self._compute_user_need_scores(cep_rules, need_weights, rule_need_map)
        print(f"  命中用户数: {len(user_need_scores):,}")

        if not user_need_scores:
            print("  [警告] 无用户命中任何规则")
            return self._empty_result(item_name, budget, target_audience_size, inferred_needs)

        # 5. 汇总每个用户的总意向分
        user_total_scores: dict[str, float] = {
            uid: sum(need_scores.values())
            for uid, need_scores in user_need_scores.items()
        }

        # 6. 确定 TopK
        cost_per_user = self.DEFAULT_CPM * self.DEFAULT_FREQ / 1000
        if target_audience_size > 0:
            k = min(target_audience_size, len(user_total_scores))
        else:
            k = min(int(budget / cost_per_user), len(user_total_scores))
        print(f"  TopK={k:,} (可用用户={len(user_total_scores):,})")

        sorted_users = sorted(user_total_scores.items(), key=lambda x: x[1], reverse=True)
        topk_users = sorted_users[:k]
        topk_ids = {uid for uid, _ in topk_users}

        # 意向分分布
        scores = [s for _, s in topk_users]
        p90 = scores[int(len(scores) * 0.1)] if scores else 0.0
        p50 = scores[int(len(scores) * 0.5)] if scores else 0.0

        # 7. 按主导需求分组
        need_groups = self._group_by_dominant_need(
            topk_ids, user_need_scores, need_weights, budget, inferred_needs
        )
        print(f"  需求分组: {[(g.need_label, g.user_count) for g in need_groups]}")

        # 8. 全局媒体/素材推荐（主导需求）
        dominant_need = inferred_needs[0] if inferred_needs else ""
        placements = self._recommend_placements(dominant_need, budget)
        creatives = self._recommend_creatives(inferred_needs, item_name)

        # 9. 效果预估
        avg_tgi = self._get_avg_tgi(cep_rules)
        global_cvr = self._storage.get_conversion_rate()
        estimated_cvr = global_cvr * (avg_tgi / 100)
        estimated_conversions = int(k * estimated_cvr)

        matched_rule_names = [r.get("name", "") for r in cep_rules
                               if any(uid in topk_ids for uid in [])][:3]

        summary = self._build_summary(
            item_name, budget, k, target_audience_size,
            inferred_needs, need_groups, estimated_conversions, avg_tgi
        )

        return StrategyResult(
            item_name=item_name,
            total_budget=budget,
            total_users=k,
            target_audience_size=target_audience_size,
            intent_score_p90=round(p90, 4),
            intent_score_p50=round(p50, 4),
            matched_rules=matched_rule_names,
            inferred_needs=inferred_needs,
            need_groups=need_groups,
            placements=placements,
            creatives=creatives,
            estimated_reach=k,
            estimated_conversions=estimated_conversions,
            avg_tgi=avg_tgi,
            summary=summary,
        )

    # ── 私有方法 ─────────────────────────────────────────────────────────────

    def _get_item_attrs(self, item_name: str) -> dict:
        onto = self._onto
        if onto is not None and hasattr(onto, "CarModel"):
            for inst in onto.CarModel.instances():
                if inst.name == item_name:
                    return {
                        "msrp": getattr(inst, "msrp", None),
                        "power_type": getattr(inst, "power_type", None),
                        "seat_layout": getattr(inst, "seat_layout", None),
                        "body_type": getattr(inst, "body_type", None),
                        "car_size_level": getattr(inst, "car_size_level", None),
                        "brand_tier": getattr(inst, "brand_tier", None),
                        "noa_level": getattr(inst, "noa_level", None),
                        "car_phone_ecosystem": getattr(inst, "car_phone_ecosystem", None),
                    }
        return {}

    def _llm_infer_targeting(self, item_name: str, item_attrs: dict) -> dict:
        """
        LLM 推断：
          1. 该 Item 对应哪些核心需求，以及每个需求的权重（0~1，和为1）
          2. 每条已发布 CEP 规则最匹配哪个需求（rule_need_map）
        """
        published_rules = self._storage.get_rules("published")
        cep_rules = [r for r in published_rules if r.get("rule_type") == "cep_clean"]
        rule_summaries = "\n".join(
            f"  - {r['name']}: {r.get('description', '')} (TGI={r.get('tgi') or 0:.0f})"
            for r in cep_rules
        ) or "（暂无已发布规则）"

        attrs_text = json.dumps(item_attrs, ensure_ascii=False) if item_attrs else "（无本体数据）"

        prompt = f"""你是汽车广告投放专家。请根据车型信息，完成以下两项任务。

## 车型
{item_name}

## 车型属性
{attrs_text}

## 已发布 CEP 行为规则
{rule_summaries}

## 任务1：推断核心需求及权重
列出该车型最相关的 2~4 个目标人群需求，用简短中文标签（如：户外越野需求、家庭空间需求、里程焦虑、预算敏感）。
为每个需求打一个权重（0~1），权重之和为 1.0，越重要权重越高。

## 任务2：规则归属需求
将每条 CEP 规则分配到最匹配的需求标签（用上面你定义的标签）。

以 JSON 返回：
{{
  "needs": [
    {{"label": "户外越野需求", "weight": 0.6}},
    {{"label": "里程焦虑", "weight": 0.4}}
  ],
  "rule_need_map": {{
    "规则名称1": "户外越野需求",
    "规则名称2": "里程焦虑"
  }},
  "reasoning": "一句话说明"
}}
只返回 JSON，不要其他文字。"""

        try:
            raw = llm_stream_call(prompt, max_tokens=1024)
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                result = json.loads(raw[start:end])
                # 归一化权重
                total_w = sum(n.get("weight", 0) for n in result.get("needs", []))
                if total_w > 0:
                    for n in result["needs"]:
                        n["weight"] = round(n["weight"] / total_w, 4)
                return result
        except Exception as e:
            print(f"  [警告] LLM 推断失败: {e}，使用规则回退")

        return self._fallback_targeting(item_name, cep_rules)

    def _fallback_targeting(self, item_name: str, cep_rules: list[dict]) -> dict:
        if any(k in item_name for k in ["猛士", "坦克", "牧马人", "越野"]):
            needs = [{"label": "户外越野需求", "weight": 0.65},
                     {"label": "里程焦虑", "weight": 0.35}]
        elif any(k in item_name for k in ["M7", "M9", "L9", "L8", "理想"]):
            needs = [{"label": "家庭空间需求", "weight": 0.6},
                     {"label": "里程焦虑", "weight": 0.4}]
        else:
            needs = [{"label": "家庭空间需求", "weight": 0.55},
                     {"label": "预算敏感", "weight": 0.45}]
        # 规则全部归到第一个需求
        rule_need_map = {r.get("name", ""): needs[0]["label"] for r in cep_rules}
        return {"needs": needs, "rule_need_map": rule_need_map, "reasoning": "规则回退"}

    def _compute_user_need_scores(
        self,
        cep_rules: list[dict],
        need_weights: dict[str, float],
        rule_need_map: dict[str, str],
    ) -> dict[str, dict[str, float]]:
        """
        计算每个用户在每个需求上的意向分。

        得分公式：
          score(user, need) += need_weight(need) × (rule.tgi / 100)
          for each rule in need that user hits

        Returns:
            {user_id: {need_label: score}}
        """
        # user_need_scores[uid][need] = score
        user_need_scores: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

        for rule in cep_rules:
            rule_name = rule.get("name", "")
            rule_tgi = float(rule.get("tgi") or 100)
            tgi_factor = rule_tgi / 100.0  # TGI=100 → 1.0，TGI=150 → 1.5

            # 确定该规则归属哪个需求
            need_label = rule_need_map.get(rule_name)
            if not need_label:
                # 未分配则归到权重最高的需求
                need_label = max(need_weights, key=need_weights.get) if need_weights else "其他"
            need_w = need_weights.get(need_label, 0.5)

            # 用规则的 sql_condition 查询命中用户
            sql_cond = rule.get("sql_condition", "")
            if not sql_cond:
                # 尝试从 conditions 字段转换
                sql_cond = self._conditions_to_sql(rule.get("conditions") or [])
            if not sql_cond:
                continue

            try:
                rows = self._storage.query(f"""
                    SELECT DISTINCT rp.user_id
                    FROM raw_profiles rp
                    LEFT JOIN raw_behaviors rb ON rp.user_id = rb.user_id
                    WHERE {sql_cond}
                """)
                contribution = need_w * tgi_factor
                for row in rows:
                    uid = row["user_id"]
                    user_need_scores[uid][need_label] += contribution
            except Exception as e:
                print(f"  [警告] 规则 '{rule_name}' 匹配失败: {e}")

        return {uid: dict(need_scores) for uid, need_scores in user_need_scores.items()}

    def _conditions_to_sql(self, conditions) -> str:
        if isinstance(conditions, str):
            try:
                conditions = json.loads(conditions)
            except Exception:
                return ""
        if not conditions:
            return ""
        parts = []
        for cond in conditions:
            if isinstance(cond, dict):
                col = cond.get("field", "")
                op = cond.get("op", "contains")
                val = cond.get("value", "")
                if not col:
                    continue
                if op == "contains":
                    parts.append(f"rb.event_raw LIKE '%{val}%'")
                elif op == "equals":
                    parts.append(f"rb.event_raw = '{val}'")
                elif op == "profile_contains":
                    parts.append(f"rp.data::VARCHAR LIKE '%{val}%'")
                elif op == "startswith":
                    parts.append(f"rb.event_raw LIKE '{val}%'")
                else:
                    parts.append(f"rb.event_raw LIKE '%{val}%'")
        return " AND ".join(parts)

    def _group_by_dominant_need(
        self,
        topk_ids: set[str],
        user_need_scores: dict[str, dict[str, float]],
        need_weights: dict[str, float],
        total_budget: float,
        inferred_needs: list[str],
    ) -> list[NeedGroup]:
        """
        对 TopK 用户按主导需求分组，按需求权重分配预算，各组独立推荐媒体/素材。
        主导需求 = 该用户得分最高的需求。
        """
        # 分组统计
        groups: dict[str, list[float]] = defaultdict(list)
        for uid in topk_ids:
            need_scores = user_need_scores.get(uid, {})
            if not need_scores:
                dominant = inferred_needs[0] if inferred_needs else "其他"
            else:
                dominant = max(need_scores, key=need_scores.get)
            total_score = sum(need_scores.values())
            groups[dominant].append(total_score)

        # 按需求权重分配预算，按组内用户数排序
        result: list[NeedGroup] = []
        total_w = sum(need_weights.get(need, 0.1) for need in groups)
        for need_label, user_scores_list in sorted(groups.items(),
                                                    key=lambda x: -len(x[1])):
            w = need_weights.get(need_label, 0.1)
            budget_share = total_budget * (w / total_w) if total_w > 0 else total_budget / len(groups)
            avg_score = sum(user_scores_list) / len(user_scores_list)
            placements = self._recommend_placements(need_label, budget_share)
            creatives = self._recommend_creatives([need_label], "")
            result.append(NeedGroup(
                need_label=need_label,
                need_weight=round(w, 4),
                user_count=len(user_scores_list),
                budget_allocated=round(budget_share),
                avg_score=round(avg_score, 4),
                placements=placements,
                creatives=creatives,
            ))

        return result

    def _get_avg_tgi(self, cep_rules: list[dict]) -> float:
        tgis = [float(r.get("tgi") or 100) for r in cep_rules if r.get("tgi")]
        return round(sum(tgis) / len(tgis), 1) if tgis else 100.0

    def _recommend_placements(self, dominant_need: str, budget: float) -> list[PlacementRec]:
        media_rules = [
            (["越野", "户外"],        [("华为智能短信", "智能短信-视频卡片", "CPM", 0.50),
                                       ("华为智能短信", "智能短信-图文卡片", "CPC", 0.30),
                                       ("华为智能短信", "智能短信", "CPM", 0.20)]),
            (["空间", "家庭"],        [("华为智能短信", "智能短信-图文卡片", "CPC", 0.45),
                                       ("华为智能短信", "智能短信", "CPM", 0.35),
                                       ("华为智能短信", "智能短信-视频卡片", "CPM", 0.20)]),
            (["预算", "价格", "敏感"], [("华为智能短信", "智能短信", "CPM", 0.50),
                                       ("华为智能短信", "智能短信-图文卡片", "CPC", 0.30),
                                       ("华为智能短信", "智能短信-视频卡片", "CPM", 0.20)]),
            (["牌照", "限牌", "指标"], [("华为智能短信", "智能短信-图文卡片", "CPC", 0.50),
                                        ("华为智能短信", "智能短信", "CPM", 0.30),
                                        ("华为智能短信", "智能短信-视频卡片", "CPM", 0.20)]),
            (["里程", "续航", "增程"], [("华为智能短信", "智能短信-视频卡片", "CPM", 0.45),
                                        ("华为智能短信", "智能短信", "CPM", 0.35),
                                        ("华为智能短信", "智能短信-图文卡片", "CPC", 0.20)]),
            (["通勤"],                [("华为智能短信", "智能短信", "CPM", 0.50),
                                       ("华为智能短信", "智能短信-图文卡片", "CPC", 0.30),
                                       ("华为智能短信", "智能短信-视频卡片", "CPM", 0.20)]),
        ]
        media_mix = next(
            (mix for kws, mix in media_rules if any(kw in dominant_need for kw in kws)),
            media_rules[0][1]
        )
        cost_per_user = self.DEFAULT_CPM * self.DEFAULT_FREQ / 1000
        return [
            PlacementRec(
                platform=m[0], ad_format=m[1], buying_type=m[2],
                budget_allocated=round(budget * m[3]),
                estimated_reach=int(budget * m[3] / cost_per_user),
                reason=f"主导需求: {dominant_need}",
            )
            for m in media_mix
        ]

    def _recommend_creatives(self, inferred_needs: list[str], item_name: str) -> list[CreativeRec]:
        onto = self._onto
        recs = []
        if onto is None or not hasattr(onto, "Creative"):
            return recs
        need_theme_keywords = [
            (["越野", "户外"],        ["越野", "军工", "硬派"]),
            (["空间", "家庭"],        ["空间", "家庭", "座"]),
            (["预算", "价格", "敏感"], ["性价比", "优惠", "降价"]),
            (["牌照", "限牌", "指标"], ["科技", "智能", "新能源"]),
            (["里程", "续航", "增程"], ["增程", "续航", "充电"]),
            (["通勤"],                ["通勤", "上班", "代步"]),
        ]
        target_themes: list[str] = []
        for need in inferred_needs[:2]:
            for need_kws, theme_kws in need_theme_keywords:
                if any(kw in need for kw in need_kws):
                    target_themes.extend(theme_kws)
                    break
        for inst in onto.Creative.instances():
            theme = getattr(inst, "theme", "") or ""
            key_message = getattr(inst, "key_message", "") or ""
            if any(t in (theme + key_message) for t in target_themes):
                recs.append(CreativeRec(
                    creative_id=getattr(inst, "creative_id", inst.name),
                    theme=theme,
                    key_message=key_message,
                    serves_need=inferred_needs[0] if inferred_needs else "",
                ))
        return recs[:3]

    def _empty_result(
        self, item_name: str, budget: float,
        target_audience_size: int, inferred_needs: list[str]
    ) -> StrategyResult:
        return StrategyResult(
            item_name=item_name, total_budget=budget, total_users=0,
            target_audience_size=target_audience_size,
            intent_score_p90=0, intent_score_p50=0,
            matched_rules=[], inferred_needs=inferred_needs,
            need_groups=[], placements=[], creatives=[],
            estimated_reach=0, estimated_conversions=0, avg_tgi=0,
            summary="暂无已发布 CEP 规则，请先运行离线 Pipeline。",
        )

    def _build_summary(
        self,
        item_name: str,
        budget: float,
        k: int,
        target_audience_size: int,
        inferred_needs: list[str],
        need_groups: list[NeedGroup],
        conversions: int,
        avg_tgi: float,
    ) -> str:
        need_str = "、".join(inferred_needs[:3]) if inferred_needs else "综合人群"
        group_str = "  ".join(
            f"{g.need_label} {g.user_count:,}人({g.user_count*100//k if k else 0}%)"
            for g in need_groups
        )
        audience_str = f"（指定 {target_audience_size:,} 人）" if target_audience_size else "（预算推算）"
        return (
            f"建议将 {budget/10000:.0f}万 预算投放给 {k:,} 位高意向用户{audience_str}，"
            f"覆盖 {need_str} 等需求，"
            f"按主导需求分组：{group_str}，"
            f"参考平均 TGI={avg_tgi:.0f}，预估转化 {conversions:,} 人。"
        )
