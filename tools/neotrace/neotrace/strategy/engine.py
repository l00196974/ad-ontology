"""
策略引擎（扁平化版）
====================
输入: item_name + budget → 输出: 完整投放策略建议

核心逻辑（去掉 NEED 中间层）：
  1. 从本体查询 Item 属性
  2. LLM 根据 Item 属性推断目标行为/画像特征 → 筛选条件 + NEED 解释标签
  3. 用已发布 CEP 规则在 raw_profiles/raw_behaviors 直接匹配用户 + 计算意向分
  4. 在预算约束下从高到低取 TopK 用户
  5. 匹配媒体（从外部接入 or 规则回退）+ 素材
  6. 输出 StrategyResult（含推导 NEED 作解释标签）
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

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
class StrategyResult:
    item_name: str
    total_budget: float
    total_users: int
    intent_score_p90: float
    intent_score_p50: float
    matched_rules: list[str]            # 命中的 CEP 规则名称列表
    inferred_needs: list[str]           # LLM 推导的需求解释标签（仅用于展示）
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

        # 1. 获取 Item 属性
        item_attrs = self._get_item_attrs(item_name)
        print(f"  Item 属性: {item_attrs}")

        # 2. LLM 推断目标行为/画像特征 + NEED 解释标签
        print(f"\n  [LLM] 推断目标人群特征...")
        targeting = self._llm_infer_targeting(item_name, item_attrs)
        inferred_needs = targeting.get("need_labels", [])
        score_weights = targeting.get("rule_weights", {})
        print(f"  推导 NEED 标签: {inferred_needs}")
        print(f"  规则权重: {score_weights}")

        # 3. 从已发布 CEP 规则匹配用户，计算意向分
        published_rules = self._storage.get_rules("published")
        cep_rules = [r for r in published_rules if r.get("rule_type") == "cep_clean"]
        print(f"  已发布 CEP 规则: {len(cep_rules)} 条")

        user_scores = self._compute_user_scores(cep_rules, score_weights)
        print(f"  参与意向评分用户数: {len(user_scores):,}")

        if not user_scores:
            print("  [警告] 无用户命中已发布 CEP 规则，请先运行离线 Pipeline")
            return self._empty_result(item_name, budget, inferred_needs)

        # 4. 预算约束 TopK 用户
        cost_per_user = self.DEFAULT_CPM * self.DEFAULT_FREQ / 1000
        k = min(int(budget / cost_per_user), len(user_scores))
        sorted_users = sorted(user_scores.items(), key=lambda x: x[1], reverse=True)
        topk_users = sorted_users[:k]

        # 意向分分布
        scores = [s for _, s in topk_users]
        p90 = scores[int(len(scores) * 0.1)] if scores else 0
        p50 = scores[int(len(scores) * 0.5)] if scores else 0

        # 5. 统计命中规则分布
        matched_rule_names = self._get_matched_rule_names(
            [uid for uid, _ in topk_users], cep_rules
        )

        # 6. 媒体推荐（基于 NEED 解释标签 + 规则回退）
        dominant_need = inferred_needs[0] if inferred_needs else "SpaceNeed"
        placements = self._recommend_placements(dominant_need, budget)

        # 7. 素材推荐
        creatives = self._recommend_creatives(inferred_needs, item_name)

        # 8. 效果预估（用已发布规则的平均 TGI）
        avg_tgi = self._get_avg_tgi(cep_rules)
        global_cvr = self._storage.get_conversion_rate()
        estimated_cvr = global_cvr * (avg_tgi / 100)
        estimated_conversions = int(k * estimated_cvr)

        summary = self._build_summary(
            item_name, budget, k, inferred_needs, matched_rule_names,
            placements, estimated_conversions, avg_tgi
        )

        return StrategyResult(
            item_name=item_name,
            total_budget=budget,
            total_users=k,
            intent_score_p90=round(p90, 3),
            intent_score_p50=round(p50, 3),
            matched_rules=matched_rule_names,
            inferred_needs=inferred_needs,
            placements=placements,
            creatives=creatives,
            estimated_reach=k,
            estimated_conversions=estimated_conversions,
            avg_tgi=avg_tgi,
            summary=summary,
        )

    # ── 私有方法 ─────────────────────────────────────────────────────────────

    def _get_item_attrs(self, item_name: str) -> dict:
        """从本体查询 Item 属性，找不到则返回空字典"""
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
        LLM 根据 Item 属性推断目标人群特征。
        返回：
          {
            "need_labels": ["OutdoorNeed", "RangeMileageAnxiety"],  # 解释用标签
            "rule_weights": {"规则名1": 0.8, "规则名2": 0.5},        # 规则匹配权重
            "reasoning": "..."
          }
        """
        published_rules = self._storage.get_rules("published")
        rule_summaries = [
            f"- {r['name']}: {r.get('description', '')} (TGI={r.get('tgi') or 0:.0f})"
            for r in published_rules if r.get("rule_type") == "cep_clean"
        ]
        rules_text = "\n".join(rule_summaries) if rule_summaries else "（暂无已发布规则）"

        attrs_text = json.dumps(item_attrs, ensure_ascii=False) if item_attrs else "（无本体数据，依赖车名推断）"

        prompt = f"""你是汽车广告投放专家。请根据以下车型信息，推断最适合的目标人群特征。

## 车型
{item_name}

## 车型属性（来自本体）
{attrs_text}

## 已有已发布的 CEP 行为规则（可用于圈人）
{rules_text}

## 任务
请：
1. 推断该车型对应的目标用户核心需求（用简短中文标签表示，例如：户外越野需求、家庭空间需求、里程焦虑、预算敏感、通勤需求、高端品质需求）
2. 从已发布 CEP 规则中，为每条规则打一个与该车型的相关度权重（0.0-1.0），越高表示越应该优先命中这条规则的用户

以 JSON 格式返回：
```json
{{
  "need_labels": ["中文需求标签1", "中文需求标签2"],
  "rule_weights": {{"规则名": 0.9, "规则名2": 0.3}},
  "reasoning": "一句话解释"
}}
```
只返回 JSON，不要其他文字。"""

        try:
            raw = llm_stream_call(prompt, max_tokens=1024)
            # 提取 JSON
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(raw[start:end])
        except Exception as e:
            print(f"\n  [警告] LLM 推断失败: {e}，使用规则回退")

        # 回退：基于车名关键词
        return self._fallback_targeting(item_name)

    def _fallback_targeting(self, item_name: str) -> dict:
        """基于车名关键词的回退推断"""
        if any(k in item_name for k in ["猛士", "坦克", "牧马人", "越野"]):
            return {
                "need_labels": ["户外越野需求", "里程焦虑"],
                "rule_weights": {},
                "reasoning": "硬派越野车，户外需求主导",
            }
        if any(k in item_name for k in ["M7", "M9", "L9", "L8", "理想"]):
            return {
                "need_labels": ["家庭空间需求", "里程焦虑"],
                "rule_weights": {},
                "reasoning": "大型 6-7 座 SUV，家庭空间需求主导",
            }
        return {
            "need_labels": ["家庭空间需求", "预算敏感"],
            "rule_weights": {},
            "reasoning": "通用推断",
        }

    def _compute_user_scores(
        self,
        cep_rules: list[dict],
        rule_weights: dict[str, float],
    ) -> dict[str, float]:
        """
        基于已发布 CEP 规则直接在 raw_profiles/raw_behaviors 匹配用户，
        计算每个用户的意向分（命中规则权重之和）。
        """
        scores: dict[str, float] = {}

        for rule in cep_rules:
            rule_name = rule.get("name", "")
            weight = rule_weights.get(rule_name, 0.5)  # 默认权重 0.5
            conditions = rule.get("conditions")
            if isinstance(conditions, str):
                try:
                    conditions = json.loads(conditions)
                except Exception:
                    conditions = []
            if not conditions:
                continue

            # 构建 SQL WHERE 子句
            sql_cond = self._conditions_to_sql(conditions)
            if not sql_cond:
                continue

            try:
                rows = self._storage.query(f"""
                    SELECT DISTINCT rp.user_id
                    FROM raw_profiles rp
                    LEFT JOIN raw_behaviors rb ON rp.user_id = rb.user_id
                    WHERE {sql_cond}
                """)
                for row in rows:
                    uid = row["user_id"]
                    scores[uid] = scores.get(uid, 0.0) + weight
            except Exception as e:
                print(f"  [警告] 规则 '{rule_name}' 匹配失败: {e}")

        return scores

    def _conditions_to_sql(self, conditions: list) -> str:
        """将规则 conditions 列表转换为 SQL WHERE 子句"""
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
            elif isinstance(cond, str):
                # 直接 SQL 片段（来自 LLM 生成的旧格式）
                parts.append(cond)
        return " AND ".join(parts) if parts else ""

    def _get_matched_rule_names(
        self, topk_user_ids: list[str], cep_rules: list[dict]
    ) -> list[str]:
        """返回 TopK 用户中命中最多的规则名称列表（Top 3）"""
        if not topk_user_ids or not cep_rules:
            return []
        uid_set = set(topk_user_ids)
        rule_hits: dict[str, int] = {}

        for rule in cep_rules:
            rule_name = rule.get("name", "")
            conditions = rule.get("conditions")
            if isinstance(conditions, str):
                try:
                    conditions = json.loads(conditions)
                except Exception:
                    conditions = []
            sql_cond = self._conditions_to_sql(conditions)
            if not sql_cond:
                continue
            try:
                rows = self._storage.query(f"""
                    SELECT DISTINCT rp.user_id
                    FROM raw_profiles rp
                    LEFT JOIN raw_behaviors rb ON rp.user_id = rb.user_id
                    WHERE {sql_cond}
                """)
                hits = sum(1 for r in rows if r["user_id"] in uid_set)
                if hits:
                    rule_hits[rule_name] = hits
            except Exception:
                pass

        return [name for name, _ in sorted(rule_hits.items(), key=lambda x: x[1], reverse=True)][:3]

    def _get_avg_tgi(self, cep_rules: list[dict]) -> float:
        """计算已发布 CEP 规则的平均 TGI"""
        tgis = [float(r.get("tgi") or 100) for r in cep_rules if r.get("tgi")]
        return round(sum(tgis) / len(tgis), 1) if tgis else 100.0

    def _recommend_placements(
        self,
        dominant_need: str,
        budget: float,
    ) -> list[PlacementRec]:
        """
        媒体推荐（规则回退）。
        基于推导的主导需求标签选择媒体组合（全部使用华为智能短信）。
        dominant_need 为中文标签，通过关键词模糊匹配选择媒体组合。
        """
        # 媒体组合规则：(平台, 广告形式, 购买方式, 预算比例)
        media_rules = [
            # 越野/户外
            (["越野", "户外"],       [("华为智能短信", "智能短信-视频卡片", "CPM", 0.50),
                                      ("华为智能短信", "智能短信-图文卡片", "CPC", 0.30),
                                      ("华为智能短信", "智能短信", "CPM", 0.20)]),
            # 空间/家庭
            (["空间", "家庭"],       [("华为智能短信", "智能短信-图文卡片", "CPC", 0.45),
                                      ("华为智能短信", "智能短信", "CPM", 0.35),
                                      ("华为智能短信", "智能短信-视频卡片", "CPM", 0.20)]),
            # 预算/价格
            (["预算", "价格", "敏感"],[("华为智能短信", "智能短信", "CPM", 0.50),
                                      ("华为智能短信", "智能短信-图文卡片", "CPC", 0.30),
                                      ("华为智能短信", "智能短信-视频卡片", "CPM", 0.20)]),
            # 牌照/限牌
            (["牌照", "限牌", "指标"],[("华为智能短信", "智能短信-图文卡片", "CPC", 0.50),
                                       ("华为智能短信", "智能短信", "CPM", 0.30),
                                       ("华为智能短信", "智能短信-视频卡片", "CPM", 0.20)]),
            # 里程/续航/增程
            (["里程", "续航", "增程"],[("华为智能短信", "智能短信-视频卡片", "CPM", 0.45),
                                       ("华为智能短信", "智能短信", "CPM", 0.35),
                                       ("华为智能短信", "智能短信-图文卡片", "CPC", 0.20)]),
            # 通勤
            (["通勤"],               [("华为智能短信", "智能短信", "CPM", 0.50),
                                      ("华为智能短信", "智能短信-图文卡片", "CPC", 0.30),
                                      ("华为智能短信", "智能短信-视频卡片", "CPM", 0.20)]),
        ]

        # 关键词模糊匹配
        media_mix = None
        for keywords, mix in media_rules:
            if any(kw in dominant_need for kw in keywords):
                media_mix = mix
                break
        if media_mix is None:
            # 默认：图文卡片为主
            media_mix = media_rules[1][1]

        cost_per_user = self.DEFAULT_CPM * self.DEFAULT_FREQ / 1000

        return [
            PlacementRec(
                platform=m[0],
                ad_format=m[1],
                buying_type=m[2],
                budget_allocated=round(budget * m[3]),
                estimated_reach=int(budget * m[3] / cost_per_user),
                reason=f"主导需求: {dominant_need}",
            )
            for m in media_mix
        ]

    def _recommend_creatives(
        self,
        inferred_needs: list[str],
        item_name: str,
    ) -> list[CreativeRec]:
        """从本体查找与主导需求匹配的素材（中文关键词匹配）"""
        onto = self._onto
        recs = []
        if onto is None or not hasattr(onto, "Creative"):
            return recs

        # 中文需求关键词 → 素材主题关键词
        need_theme_keywords = [
            (["越野", "户外"],       ["越野", "军工", "硬派"]),
            (["空间", "家庭"],       ["空间", "家庭", "座"]),
            (["预算", "价格", "敏感"],["性价比", "优惠", "降价"]),
            (["牌照", "限牌", "指标"],["科技", "智能", "新能源"]),
            (["里程", "续航", "增程"],["增程", "续航", "充电"]),
            (["通勤"],               ["通勤", "上班", "代步"]),
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
            combined = theme + key_message
            if any(t in combined for t in target_themes):
                recs.append(CreativeRec(
                    creative_id=getattr(inst, "creative_id", inst.name),
                    theme=theme,
                    key_message=key_message,
                    serves_need=inferred_needs[0] if inferred_needs else "",
                ))
        return recs[:3]

    def _empty_result(
        self, item_name: str, budget: float, inferred_needs: list[str]
    ) -> StrategyResult:
        return StrategyResult(
            item_name=item_name, total_budget=budget, total_users=0,
            intent_score_p90=0, intent_score_p50=0,
            matched_rules=[], inferred_needs=inferred_needs,
            placements=[], creatives=[], estimated_reach=0,
            estimated_conversions=0, avg_tgi=0,
            summary="暂无已发布 CEP 规则，请先运行离线 Pipeline。",
        )

    def _build_summary(
        self,
        item_name: str,
        budget: float,
        k: int,
        inferred_needs: list[str],
        matched_rules: list[str],
        placements: list,
        conversions: int,
        avg_tgi: float,
    ) -> str:
        need_str = "、".join(inferred_needs[:3]) if inferred_needs else "综合人群"
        rule_str = "、".join(matched_rules[:2]) if matched_rules else "CEP规则"
        media_str = "、".join(f"{p.platform}({p.ad_format})" for p in placements[:2])
        return (
            f"建议将 {budget/10000:.0f}万 预算投放给 {k:,} 位高意向用户，"
            f"主要覆盖 {need_str} 等需求人群，"
            f"核心圈人规则：{rule_str}，"
            f"推荐媒体：{media_str}，"
            f"参考平均 TGI={avg_tgi:.0f}，"
            f"预估转化 {conversions:,} 人。"
        )
