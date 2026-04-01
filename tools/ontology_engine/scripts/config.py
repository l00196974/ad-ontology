#!/usr/bin/env python3
"""
config.py — 统一配置层
======================

所有常量、阈值、规则定义、文件路径的唯一来源。
支持三种覆盖方式（优先级从高到低）：
  1. 运行时通过 apply_overrides(tgi_threshold=..., max_rounds=...) 显式覆盖
  2. 环境变量（TGI_THRESHOLD, MAX_ROUNDS, MIN_CONFIRMED 等）
  3. 本文件中的默认值
"""

from __future__ import annotations

import os

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ─────────────────────────────────────────────────────────────────────────────
# 推理配置
# ─────────────────────────────────────────────────────────────────────────────

TGI_THRESHOLD    = int(os.getenv("TGI_THRESHOLD", "150"))
MAX_ROUNDS       = int(os.getenv("MAX_ROUNDS", "10"))
MIN_CONFIRMED    = int(os.getenv("MIN_CONFIRMED", "30"))

# ─────────────────────────────────────────────────────────────────────────────
# 因果检验阈值
# ─────────────────────────────────────────────────────────────────────────────

CAUSAL_DIFF_MIN       = float(os.getenv("CAUSAL_DIFF_MIN", "0.05"))
CAUSAL_CTRL_DIFF_MIN  = float(os.getenv("CAUSAL_CTRL_DIFF_MIN", "0.03"))

# ─────────────────────────────────────────────────────────────────────────────
# CEP 规则阈值
# ─────────────────────────────────────────────────────────────────────────────

CEP_MULTI_DAY_MIN    = int(os.getenv("CEP_MULTI_DAY_MIN", "3"))
CEP_BRAND_SEARCH_MIN = int(os.getenv("CEP_BRAND_SEARCH_MIN", "2"))
CEP_DEALER_DUR_S     = int(os.getenv("CEP_DEALER_DUR_S", "1800"))
CEP_SEARCH_DUR_S     = int(os.getenv("CEP_SEARCH_DUR_S", "3000"))

# ─────────────────────────────────────────────────────────────────────────────
# Meta-Ontology 白名单（严格禁止在运行时新增）
# ─────────────────────────────────────────────────────────────────────────────

VALID_NODE_TYPES: set[str] = {"User", "Event", "Need", "Item", "Media"}

VALID_EDGES: dict[str, tuple[set[str], set[str]]] = {
    "Actively_Searches": ({"User"},  {"Item", "Need"}),
    "Highly_Exposed_To": ({"User"},  {"Media"}),
    "Has_Recent_Event":  ({"User"},  {"Event"}),
    "Triggers_Need":     ({"Event"}, {"Need"}),
    "Satisfied_By":      ({"Need"},  {"Item"}),
    "High_CTR_On":       ({"Need"},  {"Media"}),
    "Low_CPA_On":        ({"Need"},  {"Media"}),
}

# ─────────────────────────────────────────────────────────────────────────────
# 内置 CEP 规则（LLM 失败时的 fallback）
# 规则阈值参数引用上面的配置，延迟求值以支持运行时覆盖
# ─────────────────────────────────────────────────────────────────────────────

def get_builtin_cep_rules() -> list[dict]:
    """返回内置 CEP 规则列表，使用当前配置值（支持运行时 apply_overrides 后重新生成）"""
    return [
        {
            "name": "multi_day_search",
            "desc": f"搜索行为跨越>={CEP_MULTI_DAY_MIN}个不同日期",
            "sql": f"""
                INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
                SELECT user_id, MAX(event_time), 'multi_day_search',
                       '搜索行为跨越>={CEP_MULTI_DAY_MIN}个不同日期',
                       json_object('search_days',COUNT(DISTINCT time_str),'total_count',COUNT(*))
                FROM user_raw_events
                WHERE event_type IN ('search_vertical','search_general')
                GROUP BY user_id HAVING COUNT(DISTINCT time_str) >= {CEP_MULTI_DAY_MIN}
            """,
        },
        {
            "name": "brand_focused_search",
            "desc": f"有明确品牌意向的搜索>={CEP_BRAND_SEARCH_MIN}次",
            "sql": f"""
                INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
                SELECT user_id, MAX(event_time), 'brand_focused_search',
                       '有明确品牌意向的搜索>={CEP_BRAND_SEARCH_MIN}次',
                       json_object('count',COUNT(*),
                                   'brands',GROUP_CONCAT(DISTINCT json_extract(attr_json,'$.brand')))
                FROM user_raw_events
                WHERE event_type IN ('search_vertical','search_general')
                  AND json_extract(attr_json,'$.brand') IS NOT NULL
                GROUP BY user_id HAVING COUNT(*) >= {CEP_BRAND_SEARCH_MIN}
            """,
        },
        {
            "name": "detail_view_with_loan",
            "desc": "同时浏览车辆详情页且浏览车贷计算页",
            "sql": """
                INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
                SELECT user_id, MAX(event_time), 'detail_view_with_loan',
                       '同时浏览车辆详情页且浏览车贷计算页',
                       json_object('detail_count',SUM(event_type='view_car_detail'),
                                   'loan_count',SUM(event_type='view_loan_calc'))
                FROM user_raw_events
                WHERE event_type IN ('view_car_detail','view_loan_calc')
                GROUP BY user_id
                HAVING SUM(event_type='view_car_detail')>=1 AND SUM(event_type='view_loan_calc')>=1
            """,
        },
        {
            "name": "pass_dealership_intent",
            "desc": f"路过门店>=2次，或1次停留>{CEP_DEALER_DUR_S}s",
            "sql": f"""
                INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
                SELECT user_id, MAX(event_time), 'pass_dealership_intent',
                       '路过门店>=2次，或1次停留>{CEP_DEALER_DUR_S}s',
                       json_object('count',COUNT(*),'max_dur',MAX(dur_time))
                FROM user_raw_events
                WHERE event_type='pass_dealership'
                GROUP BY user_id HAVING COUNT(*)>=2 OR MAX(dur_time)>{CEP_DEALER_DUR_S}
            """,
        },
        {
            "name": "high_engagement_search",
            "desc": f"单次搜索停留>={CEP_SEARCH_DUR_S}秒",
            "sql": f"""
                INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
                SELECT user_id, MAX(event_time), 'high_engagement_search',
                       '单次搜索停留>={CEP_SEARCH_DUR_S}秒',
                       json_object('max_dur',MAX(dur_time),'count',COUNT(*))
                FROM user_raw_events
                WHERE event_type='search_general' AND dur_time>={CEP_SEARCH_DUR_S}
                GROUP BY user_id
            """,
        },
    ]


# ─────────────────────────────────────────────────────────────────────────────
# 内置 fallback 假设（LLM 无响应时第1轮使用）
# ─────────────────────────────────────────────────────────────────────────────

FALLBACK_HYPOTHESES: list[dict] = [
    {
        "id": "H1", "source": "fallback",
        "description": "持续搜索型用户具有多日搜索衍生事件",
        "source_node": "持续搜索型用户", "target_node": "multi_day_search",
        "edge_type": "Has_Recent_Event",
        "target_segment": "持续搜索型用户", "feature_event": "multi_day_search",
        "causal_reasoning": "该用户本身就是由 multi_day_search 定义的，定义上直接对应",
    },
    {
        "id": "H2", "source": "fallback",
        "description": "多日搜索触发购车意向需求",
        "source_node": "multi_day_search", "target_node": "购车意向需求",
        "edge_type": "Triggers_Need",
        "target_segment": "持续搜索型用户", "feature_event": "multi_day_search",
        "causal_reasoning": "持续搜索是主动信息收集行为，时序上先于留资，排除偶发性",
    },
    {
        "id": "H3", "source": "fallback",
        "description": "深度比价型用户具有详情+贷款双重浏览",
        "source_node": "深度比价型用户", "target_node": "detail_view_with_loan",
        "edge_type": "Has_Recent_Event",
        "target_segment": "深度比价型用户", "feature_event": "detail_view_with_loan",
        "causal_reasoning": "定义直接对应",
    },
    {
        "id": "H4", "source": "fallback",
        "description": "详情+贷款浏览触发金融方案需求",
        "source_node": "detail_view_with_loan", "target_node": "金融方案需求",
        "edge_type": "Triggers_Need",
        "target_segment": "深度比价型用户", "feature_event": "detail_view_with_loan",
        "causal_reasoning": "查看贷款是明确的金融需求探索行为，时序先于留资",
    },
    {
        "id": "H5", "source": "fallback",
        "description": "到店意向型用户具有高强度路过门店事件",
        "source_node": "到店意向型用户", "target_node": "pass_dealership_intent",
        "edge_type": "Has_Recent_Event",
        "target_segment": "到店意向型用户", "feature_event": "pass_dealership_intent",
        "causal_reasoning": "定义直接对应",
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# 内置 fallback Need/Item/Media 节点
# ─────────────────────────────────────────────────────────────────────────────

FALLBACK_NEED_ITEM_MEDIA: dict[str, list[str]] = {
    "Need":  ["购车意向需求", "选车比价需求", "到店体验需求", "品牌偏好需求", "金融方案需求"],
    "Item":  ["新能源轿车", "新能源SUV", "豪华品牌车型", "国产新势力车型"],
    "Media": ["搜索结果广告", "车辆详情页广告", "地图导航广告", "信息流广告"],
}

# ─────────────────────────────────────────────────────────────────────────────
# 输出文件路径
# ─────────────────────────────────────────────────────────────────────────────

CONFIRMED_RULES_PATH = os.path.join(_SCRIPT_DIR, "confirmed_rules.json")
ONTOLOGY_PATH        = os.path.join(_SCRIPT_DIR, "ontology.json")
VALIDATION_LOG_PATH  = os.path.join(_SCRIPT_DIR, "validation_log.json")
LLM_CONFIG_PATH      = os.path.join(_SCRIPT_DIR, "llm_config.json")

# ─────────────────────────────────────────────────────────────────────────────
# 运行时覆盖（支持 CLI 参数传入）
# ─────────────────────────────────────────────────────────────────────────────

def apply_overrides(
    tgi_threshold: int | None = None,
    max_rounds: int | None = None,
    min_confirmed: int | None = None,
    causal_diff_min: float | None = None,
    causal_ctrl_diff_min: float | None = None,
    cep_multi_day_min: int | None = None,
    cep_brand_search_min: int | None = None,
    cep_dealer_dur_s: int | None = None,
    cep_search_dur_s: int | None = None,
) -> None:
    """将 CLI 传入的参数覆盖到全局配置变量（仅覆盖非 None 的值）"""
    import sys
    module = sys.modules[__name__]
    pairs = [
        ("TGI_THRESHOLD",    tgi_threshold),
        ("MAX_ROUNDS",       max_rounds),
        ("MIN_CONFIRMED",    min_confirmed),
        ("CAUSAL_DIFF_MIN",  causal_diff_min),
        ("CAUSAL_CTRL_DIFF_MIN", causal_ctrl_diff_min),
        ("CEP_MULTI_DAY_MIN",  cep_multi_day_min),
        ("CEP_BRAND_SEARCH_MIN", cep_brand_search_min),
        ("CEP_DEALER_DUR_S", cep_dealer_dur_s),
        ("CEP_SEARCH_DUR_S", cep_search_dur_s),
    ]
    for name, val in pairs:
        if val is not None:
            setattr(module, name, val)
