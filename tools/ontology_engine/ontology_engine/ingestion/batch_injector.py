"""
每日批量行为事件注入器
======================
从 JSON 文件或 dict 列表加载今日用户行为事件，批量注入并返回汇总统计。

典型使用场景：
  每天凌晨从数据仓库导出昨日新增行为事件 → 写成 JSON 文件 →
  调用 inject_from_json() → 自动注入并触发增量推理

JSON 格式（events.json）：
  [
    {"user_id": "张三", "event_type": "profile_update",
     "payload": {"field": "conversion_stage", "value": "试驾"}},
    {"user_id": "李四", "event_type": "car_view",
     "payload": {"car_name": "问界M7", "power_type": "增程式", "body_type": "SUV"}},
    ...
  ]
"""

from __future__ import annotations

import json
import logging
import os

from ontology_engine.ingestion.event_types    import UserBehaviorEvent
from ontology_engine.ingestion.event_injector import EventInjector

logger = logging.getLogger(__name__)


def inject_from_json(
    path: str,
    backend: str = "graphdb",
    auto_re_infer: bool = True,
) -> dict:
    """
    从 JSON 文件加载事件列表并批量注入。

    参数：
        path          — JSON 文件路径
        backend       — "memory" | "graphdb"
        auto_re_infer — 是否自动触发增量推理（默认 True）

    返回：
        汇总统计 dict，包含：
          injected       — 成功注入的事件总数
          users_affected — 受影响的用户数
          re_inferred    — 重推理的用户数
          results        — {user_id: UserNeedResult（dict 格式）}
          errors         — 注入失败的事件列表
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"事件文件不存在：{path}")

    with open(path, "r", encoding="utf-8") as f:
        raw_events = json.load(f)

    return inject_from_dict(raw_events, backend=backend, auto_re_infer=auto_re_infer)


def inject_from_dict(
    events: list[dict],
    backend: str = "graphdb",
    auto_re_infer: bool = True,
) -> dict:
    """
    从 dict 列表批量注入事件。

    参数：
        events        — UserBehaviorEvent.from_dict() 可解析的 dict 列表
        backend       — "memory" | "graphdb"
        auto_re_infer — 是否自动触发增量推理（默认 True）

    返回：
        与 inject_from_json() 相同的汇总统计 dict
    """
    import dataclasses

    injector = EventInjector(backend=backend, auto_re_infer=False)
    errors: list[dict] = []
    valid_events: list[UserBehaviorEvent] = []

    # 解析事件（收集解析错误但不中断）
    for i, raw in enumerate(events):
        try:
            valid_events.append(UserBehaviorEvent.from_dict(raw))
        except Exception as exc:
            errors.append({"index": i, "raw": raw, "error": str(exc)})
            logger.warning("事件解析失败（index=%d）：%s", i, exc)

    # 按用户分组注入
    injected   = 0
    seen_users: list[str] = []
    seen_set:   set[str]  = set()

    for event in valid_events:
        try:
            injector.inject(event)   # auto_re_infer=False，不重推
            injected += 1
            if event.user_id not in seen_set:
                seen_set.add(event.user_id)
                seen_users.append(event.user_id)
        except Exception as exc:
            errors.append({"event": dataclasses.asdict(event), "error": str(exc)})
            logger.warning("事件注入失败（user=%s）：%s", event.user_id, exc)

    # 集中触发增量推理（每个用户只推一次）
    results: dict = {}
    if auto_re_infer:
        re_injector = EventInjector(backend=backend, auto_re_infer=True)
        for uid in seen_users:
            result = re_injector._re_infer_user(uid)
            if result is not None:
                results[uid] = dataclasses.asdict(result)

    logger.info(
        "批量注入完成：共 %d 条事件，影响 %d 个用户，重推理 %d 人，失败 %d 条",
        injected, len(seen_users), len(results), len(errors),
    )

    return {
        "injected":       injected,
        "users_affected": len(seen_users),
        "re_inferred":    len(results),
        "results":        results,
        "errors":         errors,
    }
