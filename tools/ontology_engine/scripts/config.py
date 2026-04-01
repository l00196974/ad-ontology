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

TGI_THRESHOLD    = int(os.getenv("TGI_THRESHOLD", "120"))
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
# 内置 CEP 规则（LLM 失败时的 fallback，约 35 条）
#
# 重要约束：所有规则必须在 WHERE 中排除 event_type='lead_submit'
#   lead_submit 是预测目标（留资行为），绝对不能作为特征输入，否则是数据泄露。
# ─────────────────────────────────────────────────────────────────────────────

def get_builtin_cep_rules() -> list[dict]:
    """返回内置 CEP 规则列表（约 35 条），使用当前配置值支持运行时覆盖。

    所有规则均排除 lead_submit——该事件是预测目标，不得用作特征。
    """
    X = "event_type != 'lead_submit'"  # 所有规则共用的排除条件

    return [
        # ── 搜索行为：单维度 ────────────────────────────────────────────────
        {
            "name": "multi_day_search",
            "desc": f"搜索跨越>={CEP_MULTI_DAY_MIN}个不同日期（持续关注）",
            "sql": f"""
                INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
                SELECT user_id, MAX(event_time), 'multi_day_search',
                       '跨{CEP_MULTI_DAY_MIN}天持续搜索',
                       json_object('search_days',COUNT(DISTINCT time_str),'total',COUNT(*))
                FROM user_raw_events
                WHERE event_type IN ('search_vertical','search_general') AND {X}
                GROUP BY user_id HAVING COUNT(DISTINCT time_str) >= {CEP_MULTI_DAY_MIN}
            """,
        },
        {
            "name": "brand_focused_search",
            "desc": f"有明确品牌的搜索>={CEP_BRAND_SEARCH_MIN}次",
            "sql": f"""
                INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
                SELECT user_id, MAX(event_time), 'brand_focused_search',
                       '有明确品牌搜索>={CEP_BRAND_SEARCH_MIN}次',
                       json_object('count',COUNT(*),
                                   'brands',GROUP_CONCAT(DISTINCT json_extract(attr_json,'$.brand')))
                FROM user_raw_events
                WHERE event_type IN ('search_vertical','search_general')
                  AND json_extract(attr_json,'$.brand') IS NOT NULL AND {X}
                GROUP BY user_id HAVING COUNT(*) >= {CEP_BRAND_SEARCH_MIN}
            """,
        },
        {
            "name": "high_freq_search",
            "desc": "搜索总次数>=10次（高频搜索）",
            "sql": f"""
                INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
                SELECT user_id, MAX(event_time), 'high_freq_search',
                       '搜索>=10次',
                       json_object('count',COUNT(*))
                FROM user_raw_events
                WHERE event_type IN ('search_vertical','search_general') AND {X}
                GROUP BY user_id HAVING COUNT(*) >= 10
            """,
        },
        {
            "name": "vertical_search_user",
            "desc": "三车垂媒专业搜索>=2次",
            "sql": f"""
                INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
                SELECT user_id, MAX(event_time), 'vertical_search_user',
                       '三车垂媒搜索>=2次',
                       json_object('count',COUNT(*))
                FROM user_raw_events
                WHERE event_type='search_vertical' AND {X}
                GROUP BY user_id HAVING COUNT(*) >= 2
            """,
        },
        {
            "name": "entertainment_search_user",
            "desc": "泛娱乐种草搜索>=2次（内容平台种草）",
            "sql": f"""
                INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
                SELECT user_id, MAX(event_time), 'entertainment_search_user',
                       '泛娱乐种草>=2次',
                       json_object('count',COUNT(*))
                FROM user_raw_events
                WHERE event_type='search_entertainment' AND {X}
                GROUP BY user_id HAVING COUNT(*) >= 2
            """,
        },
        {
            "name": "high_engagement_search",
            "desc": f"单次搜索停留>={CEP_SEARCH_DUR_S}秒（深度阅读）",
            "sql": f"""
                INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
                SELECT user_id, MAX(event_time), 'high_engagement_search',
                       '搜索停留>={CEP_SEARCH_DUR_S}s',
                       json_object('max_dur',MAX(dur_time),'count',COUNT(*))
                FROM user_raw_events
                WHERE event_type='search_general' AND dur_time>={CEP_SEARCH_DUR_S} AND {X}
                GROUP BY user_id
            """,
        },
        {
            "name": "multi_brand_search",
            "desc": "搜索过>=3个不同品牌（横向比较）",
            "sql": f"""
                INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
                SELECT user_id, MAX(event_time), 'multi_brand_search',
                       '搜索>=3个品牌',
                       json_object('brand_count',COUNT(DISTINCT json_extract(attr_json,'$.brand')),
                                   'brands',GROUP_CONCAT(DISTINCT json_extract(attr_json,'$.brand')))
                FROM user_raw_events
                WHERE event_type IN ('search_vertical','search_general')
                  AND json_extract(attr_json,'$.brand') IS NOT NULL AND {X}
                GROUP BY user_id
                HAVING COUNT(DISTINCT json_extract(attr_json,'$.brand')) >= 3
            """,
        },
        # ── 浏览行为：单维度 ────────────────────────────────────────────────
        {
            "name": "detail_view_user",
            "desc": "浏览车辆详情页>=2次",
            "sql": f"""
                INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
                SELECT user_id, MAX(event_time), 'detail_view_user',
                       '浏览车辆详情>=2次',
                       json_object('count',COUNT(*),
                                   'brands',GROUP_CONCAT(DISTINCT json_extract(attr_json,'$.brand')))
                FROM user_raw_events
                WHERE event_type='view_car_detail' AND {X}
                GROUP BY user_id HAVING COUNT(*) >= 2
            """,
        },
        {
            "name": "loan_calc_user",
            "desc": "浏览车贷计算页（金融决策行为）",
            "sql": f"""
                INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
                SELECT user_id, MAX(event_time), 'loan_calc_user',
                       '浏览车贷计算',
                       json_object('count',COUNT(*))
                FROM user_raw_events
                WHERE event_type='view_loan_calc' AND {X}
                GROUP BY user_id HAVING COUNT(*) >= 1
            """,
        },
        {
            "name": "car_compare_user",
            "desc": "浏览车型对比页（评估意向强）",
            "sql": f"""
                INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
                SELECT user_id, MAX(event_time), 'car_compare_user',
                       '浏览车型对比',
                       json_object('count',COUNT(*))
                FROM user_raw_events
                WHERE event_type='view_car_compare' AND {X}
                GROUP BY user_id HAVING COUNT(*) >= 1
            """,
        },
        {
            "name": "floor_price_user",
            "desc": "查落地价（进入价格决策阶段）",
            "sql": f"""
                INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
                SELECT user_id, MAX(event_time), 'floor_price_user',
                       '查落地价',
                       json_object('count',COUNT(*))
                FROM user_raw_events
                WHERE event_type='view_floor_price' AND {X}
                GROUP BY user_id HAVING COUNT(*) >= 1
            """,
        },
        {
            "name": "contact_sales_user",
            "desc": "浏览联系销售页（主动触达意向）",
            "sql": f"""
                INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
                SELECT user_id, MAX(event_time), 'contact_sales_user',
                       '浏览联系销售',
                       json_object('count',COUNT(*))
                FROM user_raw_events
                WHERE event_type='view_contact_sales' AND {X}
                GROUP BY user_id HAVING COUNT(*) >= 1
            """,
        },
        {
            "name": "short_video_car_user",
            "desc": "浏览汽车短视频>=2次（内容种草）",
            "sql": f"""
                INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
                SELECT user_id, MAX(event_time), 'short_video_car_user',
                       '浏览汽车短视频>=2次',
                       json_object('count',COUNT(*))
                FROM user_raw_events
                WHERE event_type='view_short_video' AND {X}
                GROUP BY user_id HAVING COUNT(*) >= 2
            """,
        },
        {
            "name": "multi_model_detail",
            "desc": "浏览>=3款不同车型详情（深度选车）",
            "sql": f"""
                INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
                SELECT user_id, MAX(event_time), 'multi_model_detail',
                       '浏览>=3款车型详情',
                       json_object('model_count',COUNT(DISTINCT json_extract(attr_json,'$.model')))
                FROM user_raw_events
                WHERE event_type='view_car_detail'
                  AND json_extract(attr_json,'$.model') IS NOT NULL AND {X}
                GROUP BY user_id
                HAVING COUNT(DISTINCT json_extract(attr_json,'$.model')) >= 3
            """,
        },
        # ── 广告点击维度 ────────────────────────────────────────────────────
        {
            "name": "ad_click_user",
            "desc": "点击过广告>=1次",
            "sql": f"""
                INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
                SELECT user_id, MAX(event_time), 'ad_click_user',
                       '点击广告>=1次',
                       json_object('count',COUNT(*))
                FROM user_raw_events
                WHERE event_type='ad_click' AND {X}
                GROUP BY user_id HAVING COUNT(*) >= 1
            """,
        },
        {
            "name": "multi_ad_click",
            "desc": "点击广告>=3次（高广告响应）",
            "sql": f"""
                INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
                SELECT user_id, MAX(event_time), 'multi_ad_click',
                       '点击广告>=3次',
                       json_object('count',COUNT(*),
                                   'brands',GROUP_CONCAT(DISTINCT json_extract(attr_json,'$.brand')))
                FROM user_raw_events
                WHERE event_type='ad_click' AND {X}
                GROUP BY user_id HAVING COUNT(*) >= 3
            """,
        },
        {
            "name": "brand_ad_click",
            "desc": "点击过含明确品牌的广告",
            "sql": f"""
                INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
                SELECT user_id, MAX(event_time), 'brand_ad_click',
                       '点击品牌广告',
                       json_object('count',COUNT(*),
                                   'brands',GROUP_CONCAT(DISTINCT json_extract(attr_json,'$.brand')))
                FROM user_raw_events
                WHERE event_type='ad_click'
                  AND json_extract(attr_json,'$.brand') IS NOT NULL AND {X}
                GROUP BY user_id HAVING COUNT(*) >= 1
            """,
        },
        # ── 到店 / 出行维度 ─────────────────────────────────────────────────
        {
            "name": "pass_dealership_intent",
            "desc": f"路过门店>=2次，或单次停留>{CEP_DEALER_DUR_S}s",
            "sql": f"""
                INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
                SELECT user_id, MAX(event_time), 'pass_dealership_intent',
                       '路过门店意向',
                       json_object('count',COUNT(*),'max_dur',MAX(dur_time))
                FROM user_raw_events
                WHERE event_type='pass_dealership' AND {X}
                GROUP BY user_id HAVING COUNT(*)>=2 OR MAX(dur_time)>{CEP_DEALER_DUR_S}
            """,
        },
        {
            "name": "pass_dealership_once",
            "desc": "路过门店>=1次",
            "sql": f"""
                INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
                SELECT user_id, MAX(event_time), 'pass_dealership_once',
                       '路过门店>=1次',
                       json_object('count',COUNT(*),'max_dur',MAX(dur_time))
                FROM user_raw_events
                WHERE event_type='pass_dealership' AND {X}
                GROUP BY user_id HAVING COUNT(*) >= 1
            """,
        },
        {
            "name": "map_app_power_user",
            "desc": "地图/打车软件使用>=5次（出行活跃）",
            "sql": f"""
                INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
                SELECT user_id, MAX(event_time), 'map_app_power_user',
                       '地图打车>=5次',
                       json_object('count',COUNT(*))
                FROM user_raw_events
                WHERE event_type='map_app_use' AND {X}
                GROUP BY user_id HAVING COUNT(*) >= 5
            """,
        },
        {
            "name": "rental_car_user",
            "desc": "使用过租车软件（有临时用车需求）",
            "sql": f"""
                INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
                SELECT user_id, MAX(event_time), 'rental_car_user',
                       '使用租车软件',
                       json_object('count',COUNT(*))
                FROM user_raw_events
                WHERE event_type='rental_app_use' AND {X}
                GROUP BY user_id HAVING COUNT(*) >= 1
            """,
        },
        # ── 试驾 / 大定维度 ─────────────────────────────────────────────────
        {
            "name": "test_drive_user",
            "desc": "有试驾行为（最强购车意向信号）",
            "sql": f"""
                INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
                SELECT user_id, MAX(event_time), 'test_drive_user',
                       '有试驾',
                       json_object('count',COUNT(*))
                FROM user_raw_events
                WHERE event_type='test_drive' AND {X}
                GROUP BY user_id HAVING COUNT(*) >= 1
            """,
        },
        {
            "name": "order_placed_user",
            "desc": "已大定下订（极强购买意向）",
            "sql": f"""
                INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
                SELECT user_id, MAX(event_time), 'order_placed_user',
                       '已大定下订',
                       json_object('count',COUNT(*))
                FROM user_raw_events
                WHERE event_type='order_placed' AND {X}
                GROUP BY user_id HAVING COUNT(*) >= 1
            """,
        },
        # ── 跨行为组合维度 ───────────────────────────────────────────────────
        {
            "name": "search_then_detail",
            "desc": "既搜索又浏览详情页（漏斗推进）",
            "sql": f"""
                INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
                SELECT user_id, MAX(event_time), 'search_then_detail',
                       '搜索+详情浏览',
                       json_object('search_cnt',SUM(event_type IN ('search_vertical','search_general')),
                                   'detail_cnt',SUM(event_type='view_car_detail'))
                FROM user_raw_events
                WHERE event_type IN ('search_vertical','search_general','view_car_detail') AND {X}
                GROUP BY user_id
                HAVING SUM(event_type IN ('search_vertical','search_general'))>=1
                   AND SUM(event_type='view_car_detail')>=1
            """,
        },
        {
            "name": "detail_view_with_loan",
            "desc": "浏览车辆详情页+车贷计算（财务决策）",
            "sql": f"""
                INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
                SELECT user_id, MAX(event_time), 'detail_view_with_loan',
                       '详情页+车贷计算',
                       json_object('detail_count',SUM(event_type='view_car_detail'),
                                   'loan_count',SUM(event_type='view_loan_calc'))
                FROM user_raw_events
                WHERE event_type IN ('view_car_detail','view_loan_calc') AND {X}
                GROUP BY user_id
                HAVING SUM(event_type='view_car_detail')>=1 AND SUM(event_type='view_loan_calc')>=1
            """,
        },
        {
            "name": "detail_and_compare",
            "desc": "浏览详情页+车型对比（深度评估）",
            "sql": f"""
                INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
                SELECT user_id, MAX(event_time), 'detail_and_compare',
                       '详情+车型对比',
                       json_object('detail_cnt',SUM(event_type='view_car_detail'),
                                   'compare_cnt',SUM(event_type='view_car_compare'))
                FROM user_raw_events
                WHERE event_type IN ('view_car_detail','view_car_compare') AND {X}
                GROUP BY user_id
                HAVING SUM(event_type='view_car_detail')>=1
                   AND SUM(event_type='view_car_compare')>=1
            """,
        },
        {
            "name": "detail_and_floor_price",
            "desc": "浏览详情页+查落地价（价格决策）",
            "sql": f"""
                INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
                SELECT user_id, MAX(event_time), 'detail_and_floor_price',
                       '详情+落地价',
                       json_object('detail_cnt',SUM(event_type='view_car_detail'),
                                   'price_cnt',SUM(event_type='view_floor_price'))
                FROM user_raw_events
                WHERE event_type IN ('view_car_detail','view_floor_price') AND {X}
                GROUP BY user_id
                HAVING SUM(event_type='view_car_detail')>=1
                   AND SUM(event_type='view_floor_price')>=1
            """,
        },
        {
            "name": "search_and_ad_click",
            "desc": "既搜索又点击广告（多触点响应）",
            "sql": f"""
                INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
                SELECT user_id, MAX(event_time), 'search_and_ad_click',
                       '搜索+广告点击',
                       json_object('search_cnt',SUM(event_type IN ('search_vertical','search_general')),
                                   'ad_cnt',SUM(event_type='ad_click'))
                FROM user_raw_events
                WHERE event_type IN ('search_vertical','search_general','ad_click') AND {X}
                GROUP BY user_id
                HAVING SUM(event_type IN ('search_vertical','search_general'))>=1
                   AND SUM(event_type='ad_click')>=1
            """,
        },
        {
            "name": "search_and_dealership",
            "desc": "搜索+路过门店（线上线下双触点）",
            "sql": f"""
                INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
                SELECT user_id, MAX(event_time), 'search_and_dealership',
                       '搜索+路过门店',
                       json_object('search_cnt',SUM(event_type IN ('search_vertical','search_general')),
                                   'pass_cnt',SUM(event_type='pass_dealership'))
                FROM user_raw_events
                WHERE event_type IN ('search_vertical','search_general','pass_dealership') AND {X}
                GROUP BY user_id
                HAVING SUM(event_type IN ('search_vertical','search_general'))>=1
                   AND SUM(event_type='pass_dealership')>=1
            """,
        },
        {
            "name": "contact_sales_with_detail",
            "desc": "浏览联系销售+车辆详情（主动接触）",
            "sql": f"""
                INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
                SELECT user_id, MAX(event_time), 'contact_sales_with_detail',
                       '联系销售+详情',
                       json_object('contact_cnt',SUM(event_type='view_contact_sales'),
                                   'detail_cnt',SUM(event_type='view_car_detail'))
                FROM user_raw_events
                WHERE event_type IN ('view_contact_sales','view_car_detail') AND {X}
                GROUP BY user_id
                HAVING SUM(event_type='view_contact_sales')>=1
                   AND SUM(event_type='view_car_detail')>=1
            """,
        },
        {
            "name": "video_then_search",
            "desc": "看短视频+搜索（种草转主动意向）",
            "sql": f"""
                INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
                SELECT user_id, MAX(event_time), 'video_then_search',
                       '短视频+搜索',
                       json_object('video_cnt',SUM(event_type='view_short_video'),
                                   'search_cnt',SUM(event_type IN ('search_vertical','search_general')))
                FROM user_raw_events
                WHERE event_type IN ('view_short_video','search_vertical','search_general') AND {X}
                GROUP BY user_id
                HAVING SUM(event_type='view_short_video')>=1
                   AND SUM(event_type IN ('search_vertical','search_general'))>=1
            """,
        },
        {
            "name": "test_drive_with_search",
            "desc": "试驾+搜索（体验后持续关注）",
            "sql": f"""
                INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
                SELECT user_id, MAX(event_time), 'test_drive_with_search',
                       '试驾+搜索',
                       json_object('drive_cnt',SUM(event_type='test_drive'),
                                   'search_cnt',SUM(event_type IN ('search_vertical','search_general')))
                FROM user_raw_events
                WHERE event_type IN ('test_drive','search_vertical','search_general') AND {X}
                GROUP BY user_id
                HAVING SUM(event_type='test_drive')>=1
                   AND SUM(event_type IN ('search_vertical','search_general'))>=1
            """,
        },
        {
            "name": "map_and_dealership",
            "desc": "地图导航+路过门店（出行场景到店）",
            "sql": f"""
                INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
                SELECT user_id, MAX(event_time), 'map_and_dealership',
                       '地图+路过门店',
                       json_object('map_cnt',SUM(event_type='map_app_use'),
                                   'pass_cnt',SUM(event_type='pass_dealership'))
                FROM user_raw_events
                WHERE event_type IN ('map_app_use','pass_dealership') AND {X}
                GROUP BY user_id
                HAVING SUM(event_type='map_app_use')>=1
                   AND SUM(event_type='pass_dealership')>=1
            """,
        },
        {
            "name": "full_funnel_user",
            "desc": "搜索+详情+贷款+路过门店（全漏斗覆盖）",
            "sql": f"""
                INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
                SELECT user_id, MAX(event_time), 'full_funnel_user',
                       '全漏斗覆盖',
                       json_object('search_cnt',SUM(event_type IN ('search_vertical','search_general')),
                                   'detail_cnt',SUM(event_type='view_car_detail'),
                                   'loan_cnt',SUM(event_type='view_loan_calc'),
                                   'pass_cnt',SUM(event_type='pass_dealership'))
                FROM user_raw_events
                WHERE event_type IN ('search_vertical','search_general',
                                     'view_car_detail','view_loan_calc','pass_dealership')
                  AND {X}
                GROUP BY user_id
                HAVING SUM(event_type IN ('search_vertical','search_general'))>=1
                   AND SUM(event_type='view_car_detail')>=1
                   AND SUM(event_type='view_loan_calc')>=1
                   AND SUM(event_type='pass_dealership')>=1
            """,
        },
        # ── 行为强度 / 时序维度 ──────────────────────────────────────────────
        {
            "name": "high_total_actions",
            "desc": "总行为次数>=20次（高活跃用户）",
            "sql": f"""
                INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
                SELECT user_id, MAX(event_time), 'high_total_actions',
                       '总行为>=20次',
                       json_object('total',COUNT(*))
                FROM user_raw_events
                WHERE {X}
                GROUP BY user_id HAVING COUNT(*) >= 20
            """,
        },
        {
            "name": "multi_event_type_user",
            "desc": "覆盖>=4种不同行为类型（广度覆盖）",
            "sql": f"""
                INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
                SELECT user_id, MAX(event_time), 'multi_event_type_user',
                       '>=4种行为类型',
                       json_object('type_count',COUNT(DISTINCT event_type))
                FROM user_raw_events
                WHERE {X}
                GROUP BY user_id
                HAVING COUNT(DISTINCT event_type) >= 4
            """,
        },
        {
            "name": "long_total_duration",
            "desc": "累计行为时长>=3600秒（深度投入）",
            "sql": f"""
                INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
                SELECT user_id, MAX(event_time), 'long_total_duration',
                       '累计时长>=3600s',
                       json_object('total_dur',ROUND(SUM(dur_time),0))
                FROM user_raw_events
                WHERE {X} AND dur_time > 0
                GROUP BY user_id HAVING SUM(dur_time) >= 3600
            """,
        },
        {
            "name": "recent_30day_multi_action",
            "desc": "近30天内>=3种不同行为类型（近期活跃）",
            "sql": f"""
                INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
                SELECT user_id, MAX(event_time), 'recent_30day_multi_action',
                       '近30天>=3种行为',
                       json_object('action_types',COUNT(DISTINCT event_type))
                FROM user_raw_events
                WHERE {X}
                  AND time_str >= strftime('%Y%m%d', date('now','-30 days'))
                GROUP BY user_id
                HAVING COUNT(DISTINCT event_type) >= 3
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
        "source_node": "multi_day_search", "target_node": "购车意向需求",
        "edge_type": "Triggers_Need",
        "target_segment": "multi_day_search", "feature_event": "multi_day_search",
        "causal_reasoning": "持续搜索是主动信息收集行为，时序上先于留资，排除偶发性",
    },
    {
        "id": "H2", "source": "fallback",
        "description": "详情+贷款浏览触发金融方案需求",
        "source_node": "detail_view_with_loan", "target_node": "金融方案需求",
        "edge_type": "Triggers_Need",
        "target_segment": "detail_view_with_loan", "feature_event": "detail_view_with_loan",
        "causal_reasoning": "查看贷款是明确的金融需求探索行为，时序先于留资",
    },
    {
        "id": "H3", "source": "fallback",
        "description": "路过门店触发到店体验需求",
        "source_node": "pass_dealership_intent", "target_node": "到店体验需求",
        "edge_type": "Triggers_Need",
        "target_segment": "pass_dealership_intent", "feature_event": "pass_dealership_intent",
        "causal_reasoning": "物理路过门店是线下意向的直接体现，时序先于留资",
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
