#!/usr/bin/env python3
"""
llm_client.py — LLM 调用层
===========================

职责：
  - llm_call：统一 LLM 调用入口（读 config.LLM_CONFIG_PATH）
  - parse_json_block：从 LLM 返回文本中提取 JSON
  - derive_cep_rules：让 LLM 根据事件分布推导 CEP 规则
  - derive_need_item_media：让 LLM 推导 Need/Item/Media 节点
"""

from __future__ import annotations

import json
import os
import sqlite3

import networkx as nx

import config

_LLM_CONFIG: dict | None = None


# ─────────────────────────────────────────────────────────────────────────────
# 核心调用
# ─────────────────────────────────────────────────────────────────────────────

def _load_llm_config() -> dict | None:
    global _LLM_CONFIG
    if _LLM_CONFIG is not None:
        return _LLM_CONFIG
    if os.path.exists(config.LLM_CONFIG_PATH):
        with open(config.LLM_CONFIG_PATH, encoding="utf-8") as f:
            _LLM_CONFIG = json.load(f)
    return _LLM_CONFIG


def llm_call(prompt: str) -> str | None:
    """发起 LLM 调用，返回文本内容；配置缺失或调用失败返回 None"""
    cfg = _load_llm_config()
    if not cfg or not cfg.get("api_key"):
        return None
    timeout = cfg.get("timeout", 60)
    try:
        from openai import OpenAI
        client = OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"], timeout=timeout)
        resp = client.chat.completions.create(
            model=cfg["model"],
            max_tokens=cfg.get("max_tokens", 4096),
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content
    except Exception as e:
        print(f"  [LLM] 调用失败: {e}")
        return None


def parse_json_block(text: str) -> list | dict | None:
    """从 LLM 返回文本中提取第一个 JSON 数组或对象"""
    for start, end in [("[", "]"), ("{", "}")]:
        s = text.find(start)
        e = text.rfind(end) + 1
        if s >= 0 and e > s:
            try:
                return json.loads(text[s:e])
            except Exception:
                pass
    return None


# ─────────────────────────────────────────────────────────────────────────────
# CEP 规则推导
# ─────────────────────────────────────────────────────────────────────────────

def derive_cep_rules(con: sqlite3.Connection) -> list[dict] | None:
    """
    让 LLM 根据数据中的事件分布推导 CEP 规则。
    返回规则列表（每条含 name/desc/sql）或 None（LLM 失败/返回无效）。
    """
    print("  [0B] 统计事件分布...", end="", flush=True)
    rows = con.execute("""
        SELECT e.event_type,
               COUNT(*) total_events,
               COUNT(DISTINCT e.user_id) users,
               AVG(p.is_lead) lead_rate
        FROM user_raw_events e
        JOIN user_profile p ON e.user_id=p.user_id
        WHERE e.event_type != 'lead_submit'
        GROUP BY e.event_type ORDER BY total_events DESC
    """).fetchall()
    baseline = con.execute("SELECT AVG(is_lead) FROM user_profile").fetchone()[0] or 0

    print("\r  [0B] 统计停留时长...", end="", flush=True)
    dur_rows = con.execute("""
        SELECT event_type,
               ROUND(AVG(dur_time),1) avg_dur,
               ROUND(MAX(dur_time),1) max_dur,
               ROUND(MIN(dur_time),1) min_dur
        FROM user_raw_events WHERE dur_time>0
        GROUP BY event_type ORDER BY avg_dur DESC
    """).fetchall()
    print("\r  [0B] 事件统计完成，准备调用 LLM...", flush=True)

    event_dist = "\n".join(
        f"  {r[0]:<25s} 事件数={r[1]:,} 用户数={r[2]:,} 留资率={r[3]:.2%}"
        for r in rows
    )
    dur_dist = "\n".join(
        f"  {r[0]:<25s} avg_dur={r[1]}s  max_dur={r[2]}s"
        for r in dur_rows
    )

    prompt = f"""你是汽车营销数据挖掘专家。根据以下用户行为事件的统计分布，推导 CEP（复杂事件处理）规则，
用于从原始事件中计算"高购车意向"的衍生事件，以便识别留资线索用户。

【事件类型分布（含留资率）】
{event_dist}

【事件停留时长分布（秒）】
{dur_dist}

【全量留资基线】{baseline:.2%}

【可用的原始事件类型】
  search_vertical（三车垂媒搜索）, search_general（泛资讯搜索）,
  search_entertainment（泛娱乐种草搜索）,
  view_car_detail（浏览车辆详情）, view_car_compare（浏览车型对比）,
  view_loan_calc（浏览车贷计算）, view_short_video（浏览短视频）,
  view_contact_sales（联系销售）, view_floor_price（查落地价）,
  test_drive（试驾）, order_placed（大定下订）, ad_click（广告点击）,
  pass_dealership（路过门店）, map_app_use（地图/打车软件）, rental_app_use（租车软件）

【要求】
1. 推导 5~8 条 CEP 规则，每条规则产生一个新的衍生事件类型（derived_event_type）
2. 规则必须能直接翻译为 SQL GROUP BY + HAVING 语句（基于 user_raw_events 表）
3. 衍生事件名称使用英文下划线（如 multi_day_search）
4. 规则阈值要基于上面的数据分布来设定，而非拍脑袋
5. 留资率高于基线的事件组合优先作为触发条件

【user_raw_events 表结构】
  user_id TEXT, event_time TEXT, time_str TEXT(YYYYMMDD),
  dur_time REAL(秒), event_type TEXT, attr_json TEXT

返回 JSON 数组，每条包含：
  name（衍生事件名）, desc（中文描述）, sql（INSERT INTO user_derived_events 的完整SQL）

SQL 模板：
  INSERT INTO user_derived_events(user_id,event_time,derived_event_type,source_rule,attr_json)
  SELECT user_id, MAX(event_time), '<name>', '<desc>', json_object(...)
  FROM user_raw_events WHERE ... GROUP BY user_id HAVING ...

只返回 JSON，不要其他文字。"""

    raw = llm_call(prompt)
    if not raw:
        return None
    result = parse_json_block(raw)
    if isinstance(result, list) and result:
        valid = [r for r in result if r.get("name") and r.get("sql")]
        if valid:
            return valid
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Need/Item/Media 节点推导
# ─────────────────────────────────────────────────────────────────────────────

def derive_need_item_media(con: sqlite3.Connection, G: nx.DiGraph) -> dict | None:
    """
    让 LLM 根据数据中的品牌/车型分布推导 Need/Item/Media 节点。
    返回 {"Need": [...], "Item": [...], "Media": [...]} 或 None。
    """
    print("  [1] 统计品牌/车型分布...", end="", flush=True)
    brand_rows = con.execute("""
        SELECT json_extract(attr_json,'$.brand') brand, COUNT(*) n
        FROM user_raw_events
        WHERE event_type IN ('search_vertical','search_general','view_car_detail')
          AND json_extract(attr_json,'$.brand') IS NOT NULL
        GROUP BY brand ORDER BY n DESC LIMIT 20
    """).fetchall()
    model_rows = con.execute("""
        SELECT json_extract(attr_json,'$.model') model, COUNT(*) n
        FROM user_raw_events
        WHERE event_type='view_car_detail'
          AND json_extract(attr_json,'$.model') IS NOT NULL
        GROUP BY model ORDER BY n DESC LIMIT 15
    """).fetchall()
    seg_rows = con.execute("""
        SELECT s.segment, AVG(p.is_lead) lr
        FROM user_segments s JOIN user_profile p ON s.user_id=p.user_id
        GROUP BY s.segment ORDER BY lr DESC
    """).fetchall()

    brand_summary = ", ".join(f"{r[0]}({r[1]:,}次)" for r in brand_rows)
    model_summary = ", ".join(f"{r[0]}({r[1]:,}次)" for r in model_rows)
    seg_summary   = "\n".join(f"  {r[0]}: 留资率={r[1]:.2%}" for r in seg_rows)
    print("\r  [1] 品牌/车型统计完成，准备调用 LLM...", flush=True)

    prompt = f"""你是汽车营销本体专家。请根据以下用户行为数据，推导本体中 Need（需求）、Item（产品）、Media（媒介）节点。

【用户搜索/浏览的主要品牌（Top20）】
{brand_summary}

【用户浏览的主要车型（Top15）】
{model_summary}

【当前人群分层及留资率】
{seg_summary}

【要求】
1. Need：推导 4~6 个用户购车决策中的核心需求类型（抽象层面，非具体品牌）
2. Item：推导 4~6 个产品品类节点（基于真实品牌/车型聚类，而非品牌名本身）
3. Media：推导 3~5 个广告投放媒介节点（结合购车决策场景）
4. 节点名称使用中文，简洁明了

返回 JSON 对象，格式：
{{"Need": ["需求1","需求2",...], "Item": ["品类1","品类2",...], "Media": ["媒介1","媒介2",...]}}

只返回 JSON。"""

    raw = llm_call(prompt)
    if not raw:
        return None
    result = parse_json_block(raw)
    if isinstance(result, dict) and "Need" in result:
        return result
    return None
