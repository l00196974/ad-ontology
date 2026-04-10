"""
CEP 行为清洗规则挖掘器
======================
流程：
  1. DataProfiler 统计原始行为分布
  2. LLM 基于分布 → 推荐 CEP 清洗规则（将零散行为抽象为语义事件）
  3. 对每条规则执行 SQL 条件 → 计算 TGI
  4. 保存到 RuleStore（draft 状态）供人工审核

CEP 清洗规则产出的是"语义事件"，例如：
  原始: 用户一天内多次 APP 浏览 → 语义: frequent_app_browse
  原始: 支付行为发起方是打车APP → 语义: ride_hailing_behavior
"""
from __future__ import annotations

import json

from neotrace.storage.base import StorageAdapter
from neotrace.mining.stats import DataProfiler
from neotrace.llm_client import llm_stream_call


class CepMiner:

    # 每次 LLM 推荐的规则数量
    RULES_PER_CALL = 5

    def __init__(self, storage: StorageAdapter):
        self._storage = storage
        self._profiler = DataProfiler(storage)

    def mine(self, n_rules: int = 10) -> list[dict]:
        """
        挖掘 CEP 行为清洗规则。

        Returns:
            list of rule dicts，已保存为 draft，含 tgi 计算结果
        """
        print("[CepMiner] 统计数据分布...")
        profile_result = self._profiler.profile()
        summary = profile_result["summary_text"]

        print(f"[CepMiner] 调用 LLM 生成 CEP 清洗规则 (目标 {n_rules} 条)...")
        candidates = self._generate_rules(summary, n_rules)
        print(f"  LLM 返回 {len(candidates)} 条候选规则")

        results = []
        for rule in candidates:
            # 计算 TGI
            tgi_result = self._compute_rule_tgi(rule)
            rule["tgi"] = tgi_result["tgi"]
            rule["support"] = tgi_result["support"]
            rule["hit_users"] = tgi_result["hit_users"]
            rule["rule_type"] = "cep_clean"
            rule["status"] = "draft"

            rule_id = self._storage.save_rule(rule)
            rule["rule_id"] = rule_id
            results.append(rule)

            print(f"  [{rule['name']}] TGI={rule['tgi']:.1f}, "
                  f"覆盖={rule['support']:.1%}, 命中={rule['hit_users']:,}人")

        return results

    def _generate_rules(self, data_summary: str, n_rules: int) -> list[dict]:
        """调用 LLM 推荐 CEP 清洗规则（流式）"""
        prompt = f"""你是汽车营销数据专家。基于以下数据分布，推荐 {n_rules} 条行为清洗 CEP 规则。

数据分布：
{data_summary}

CEP 行为清洗规则的目标：将原始零散行为抽象为高质量语义事件。
例如：
- "用户同一天内多次（≥3次）打开汽车APP" → 语义事件 "frequent_app_browse"
- "用户的支付行为来自打车类APP" → 语义事件 "ride_hailing_behavior"
- "用户在30天内询价同一价格带 ≥2 次" → 语义事件 "repeated_price_inquiry"

每条规则必须：
1. 基于行为特征（事件类型、事件关键词、事件频次）或画像特征（年龄段、性别、城市等），不得使用 user_id
2. 产出一个语义化的 event_type（英文下划线，如 frequent_app_browse）
3. 有业务含义解释

⚠️ 严禁在 sql_condition 中出现 user_id 或任何具体用户标识符，这会导致规则过拟合，完全失去泛化能力。
规则只能描述"发生了什么行为"或"用户属于什么人群"，而不是"哪个用户"。

请以 JSON 数组返回，每条规则格式：
{{
  "name": "规则名称",
  "description": "业务含义说明",
  "event_type": "产出的语义事件类型（英文）",
  "conditions": [
    {{"field": "字段名", "op": ">=|<=|==|in|contains", "value": "值"}}
  ],
  "sql_condition": "SQL WHERE 条件，作用于以下联表查询的别名：rp=raw_profiles（字段：data JSON, is_converted），rb=raw_behaviors（字段：event_raw, event_time）。用 json_extract_string(rp.data, '$.字段名') 读取画像字段，用 rb.event_raw LIKE '%关键词%' 匹配行为，用 COUNT(*) OVER (PARTITION BY rp.user_id) 统计频次。例如：json_extract_string(rp.data, '$.婚恋状态') = '已婚' AND rb.event_raw LIKE '%车贷%'"
}}

只返回 JSON 数组，不要其他内容。"""

        text = llm_stream_call(prompt, max_tokens=4096)
        return self._parse_json(text)

    def _parse_json(self, text: str) -> list[dict]:
        """从 LLM 响应中提取 JSON"""
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            print(f"  [警告] LLM 返回解析失败，原始内容: {text[:200]}")
            return []

    def _compute_rule_tgi(self, rule: dict, split: str | None = "train") -> dict:
        """计算规则命中用户的 TGI（默认在训练集上计算）"""
        sql_cond = rule.get("sql_condition", "1=1")
        try:
            return self._storage.compute_tgi(sql_cond, split=split)
        except Exception as e:
            print(f"  [警告] TGI 计算失败 ({rule.get('name')}): {e}")
            return {"tgi": 0, "support": 0, "hit_users": 0,
                    "hit_conversion_rate": 0, "global_conversion_rate": 0}

