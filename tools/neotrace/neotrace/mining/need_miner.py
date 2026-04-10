"""
NEED 人群规则挖掘器
===================
在 CEP 清洗规则发布后运行。
流程：
  1. 读取已发布的 CEP 规则（语义事件类型列表）
  2. 从语义事件流 PIVOT 重建宽表（feature_wide_view）
  3. LLM 基于（画像字段 + 语义事件列 + 数据分布）→ 推荐 NEED 人群圈选规则
  4. 每条 NEED 规则计算 TGI，保存为 draft

NEED 规则 = 画像条件 + CEP 行为条件 的组合，
例如：
  "中坚家庭（35-54岁）AND 有 frequent_app_browse AND 有 repeated_price_inquiry"
  → NEED: 空间刚需人群（SpaceNeed）
"""
from __future__ import annotations

import json

from neotrace.storage.base import StorageAdapter
from neotrace.llm_client import llm_stream_call


# 预定义 NEED 类型（可扩展）
NEED_TYPES = [
    {"label": "LicensePlateUrgency", "name": "牌照刚需", "desc": "受城市限牌限行政策驱动的购车需求"},
    {"label": "SpaceNeed",           "name": "空间刚需", "desc": "家庭出行需要 6-7 座大空间车型"},
    {"label": "BudgetSensitivity",   "name": "预算敏感", "desc": "价格是首要决策因子，对价格变动敏感"},
    {"label": "RangeMileageAnxiety", "name": "里程焦虑", "desc": "对纯电续航顾虑，倾向燃油或增程"},
    {"label": "LongCommuteNeed",     "name": "通勤需求", "desc": "通勤距离长，对续航/补能便利性敏感"},
]


class NeedMiner:

    RULES_PER_NEED = 2   # 每个 NEED 类型生成的规则数

    def __init__(self, storage: StorageAdapter):
        self._storage = storage

    def mine(self) -> list[dict]:
        """
        基于已发布 CEP 规则 + 画像字段，挖掘 NEED 人群规则。

        Returns:
            list of need_rule dicts（draft 状态，含 TGI）
        """
        # 1. 重建宽表（纳入最新语义事件）
        print("[NeedMiner] 重建语义特征宽表...")
        self._storage.rebuild_feature_wide_table()

        # 2. 收集已发布 CEP 规则的 event_type
        published_cep = self._storage.get_rules("published")
        cep_event_types = [r["name"] for r in published_cep if r["rule_type"] == "cep_clean"]
        print(f"  已发布 CEP 事件类型: {cep_event_types}")

        # 3. 获取画像 schema
        profile_schema = self._storage.get_profile_schema()

        results = []
        for need_type in NEED_TYPES:
            print(f"\n[NeedMiner] 挖掘 NEED: {need_type['name']}...")
            candidates = self._generate_need_rules(
                need_type, profile_schema, cep_event_types
            )

            for rule in candidates:
                tgi_result = self._compute_tgi(rule)
                rule["tgi"] = tgi_result["tgi"]
                rule["support"] = tgi_result["support"]
                rule["hit_users"] = tgi_result["hit_users"]
                rule["rule_type"] = "need_segment"
                rule["need_label"] = need_type["label"]
                rule["status"] = "draft"

                rule_id = self._storage.save_rule(rule)
                rule["rule_id"] = rule_id
                results.append(rule)

                print(f"  [{rule['name']}] TGI={rule['tgi']:.1f}, "
                      f"覆盖={rule['support']:.1%}, 命中={rule['hit_users']:,}人")

        return results

    def _generate_need_rules(
        self,
        need_type: dict,
        profile_schema: dict,
        cep_event_types: list[str],
    ) -> list[dict]:
        """调用 LLM 为指定 NEED 生成圈选规则（流式）"""
        schema_desc = "\n".join(f"  {k}: {v}" for k, v in profile_schema.items())
        events_desc = (
            "\n".join(f"  {e}: boolean" for e in cep_event_types)
            if cep_event_types else "  （暂无已发布语义事件，仅使用画像字段）"
        )

        prompt = f"""你是汽车营销数据专家。请为以下 NEED 人群设计 {self.RULES_PER_NEED} 条圈选规则。

NEED 类型：{need_type['name']}
业务含义：{need_type['desc']}

可用的用户画像字段：
{schema_desc}

可用的语义行为字段（来自 CEP 清洗，均为 boolean）：
{events_desc}

圈选规则要求：
- 组合画像字段 + 语义行为字段
- 规则要有业务逻辑依据，能解释为什么这类用户有该 NEED
- sql_condition 作用于 feature_wide_view（宽表，含所有画像字段和行为 boolean 列）
  用 json_extract_string(profile_json, '$.字段名') 读取画像字段
  用 boolean 列名直接引用行为字段，例如 married_browse_loan = true

返回 JSON 数组，格式：
{{
  "name": "规则名称",
  "description": "为什么这类用户有此 NEED",
  "conditions": [
    {{"field": "字段名", "op": "==|>=|in|==true", "value": "值"}}
  ],
  "sql_condition": "直接可执行的 WHERE 子句"
}}

只返回 JSON 数组。"""

        text = llm_stream_call(prompt, max_tokens=2048)
        return self._parse_json(text)

    def _parse_json(self, text: str) -> list[dict]:
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            print(f"  [警告] LLM 返回解析失败: {text[:200]}")
            return []

    def _compute_tgi(self, rule: dict) -> dict:
        sql_cond = rule.get("sql_condition", "1=1")
        try:
            return self._storage.compute_tgi(sql_cond)
        except Exception as e:
            print(f"  [警告] TGI 计算失败 ({rule.get('name')}): {e}")
            return {"tgi": 0, "support": 0, "hit_users": 0,
                    "hit_conversion_rate": 0, "global_conversion_rate": 0}

