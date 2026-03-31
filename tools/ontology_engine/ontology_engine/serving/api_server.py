"""
FastAPI REST API 服务
=====================
将推理引擎能力暴露为 HTTP 接口，供外部系统（广告投放平台、实验平台等）直接调用。

启动方式：
    uvicorn ontology_engine.serving.api_server:app --host 0.0.0.0 --port 8100

端点一览：
    POST /infer/{user_id}      — （可选先注入事件）重推理并返回最新需求标签
    GET  /needs/{user_id}      — 读取已有推理结果（不重推）
    POST /inject               — 注入单条行为事件
    POST /inject/batch         — 批量注入行为事件
    POST /rules/register       — 热加载新推理规则并可选触发增量重推理
    GET  /rules                — 查询已注册规则列表
    GET  /health               — 服务健康状态
"""

from __future__ import annotations

import dataclasses
import logging
import os
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

app = FastAPI(
    title="汽车营销本体推理引擎 API",
    description="提供用户需求推理、行为事件注入、规则热加载等能力",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 全局服务实例（延迟初始化，避免 import 时就加载本体）───────────────────────

_BACKEND = os.getenv("ONTOLOGY_BACKEND", "memory")


def _get_inference_service():
    from ontology_engine.serving.inference_service import InferenceService
    return InferenceService(backend=_BACKEND)


# ── Pydantic 请求 / 响应模型 ─────────────────────────────────────────────────

class EventPayload(BaseModel):
    user_id:    str
    event_type: str = Field(..., description="profile_update | car_view | journey_event")
    payload:    dict
    timestamp:  str | None = None


class InferRequest(BaseModel):
    event:         EventPayload | None = None
    force_refresh: bool               = False


class RegisterRuleRequest(BaseModel):
    rule_code:     str
    auto_re_infer: bool = True


class InjectBatchRequest(BaseModel):
    events: list[EventPayload]


# ── 辅助：UserBehaviorEvent 转换 ─────────────────────────────────────────────

def _to_event(ep: EventPayload):
    from ontology_engine.ingestion.event_types import UserBehaviorEvent
    d = ep.model_dump()
    d.pop("timestamp", None)
    if ep.timestamp:
        d["timestamp"] = ep.timestamp
    return UserBehaviorEvent.from_dict(d)


# ── 端点实现 ─────────────────────────────────────────────────────────────────

@app.post("/infer/{user_id}", summary="推理用户需求标签（可先注入事件）")
async def infer_user(user_id: str, body: InferRequest | None = None) -> dict:
    """
    对指定用户执行推理，返回 UserNeedResult JSON。

    - 若 body.event 不为空，先注入该事件，再重推理
    - force_refresh=True 强制清除旧结果并重推
    """
    try:
        svc = _get_inference_service()
        if body and body.event:
            event  = _to_event(body.event)
            result = svc.infer_and_inject(event)
        else:
            force = body.force_refresh if body else False
            result = svc.infer_single(user_id, force_refresh=force)
        return dataclasses.asdict(result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        logger.exception("推理失败：%s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/needs/{user_id}", summary="读取已有推理结果（不重推）")
async def get_needs(user_id: str) -> dict:
    """直接读取用户已有的推理结果，不触发重推理。"""
    try:
        from ontology_engine.query.user_need_query import get_user_needs
        result = get_user_needs(user_id, backend=_BACKEND)
        return dataclasses.asdict(result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        logger.exception("查询失败：%s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/inject", summary="注入单条用户行为事件")
async def inject_event(body: EventPayload) -> dict:
    """
    注入单条行为事件并返回状态。
    默认 auto_re_infer=True，注入后对该用户触发增量推理。
    """
    try:
        from ontology_engine.ingestion.event_injector import EventInjector
        event    = _to_event(body)
        injector = EventInjector(backend=_BACKEND, auto_re_infer=True)
        result   = injector.inject(event)
        return {
            "status":      "ok",
            "user_id":     body.user_id,
            "re_inferred": result is not None,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("注入失败：%s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/inject/batch", summary="批量注入用户行为事件")
async def inject_batch(body: InjectBatchRequest) -> dict:
    """批量注入事件列表，每个用户只重推一次。"""
    try:
        from ontology_engine.ingestion.batch_injector import inject_from_dict
        raw = [e.model_dump() for e in body.events]
        return inject_from_dict(raw, backend=_BACKEND, auto_re_infer=True)
    except Exception as e:
        logger.exception("批量注入失败：%s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/rules/register", summary="热加载新推理规则")
async def register_rule(body: RegisterRuleRequest) -> dict:
    """
    动态加载 BaseRule 子类代码并注册到规则引擎。
    若 auto_re_infer=True，注册后对受影响用户触发增量重推理。
    """
    try:
        from ontology_engine.rules.rule_updater import RuleUpdater
        from ontology_engine.llm.rule_sandbox   import RuleSandbox

        # 先用沙箱验证安全性（无测试用例，仅做语法+安全检查）
        sandbox = RuleSandbox()
        vr      = sandbox.validate(body.rule_code, test_cases=[])
        if not vr.passed:
            raise HTTPException(
                status_code=400,
                detail={"message": "规则代码未通过沙箱验证", "errors": vr.errors}
            )

        updater = RuleUpdater()
        rule    = updater.register_rule_from_code(body.rule_code)
        diff    = {}

        if body.auto_re_infer:
            diff = updater.re_infer_affected([rule.rule_id], backend=_BACKEND)

        return {
            "rule_id":       rule.rule_id,
            "affected_users": len(diff),
            "diff":          diff,
        }
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("规则注册失败：%s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/rules", summary="查询已注册规则列表")
async def list_rules() -> list[dict]:
    """返回当前注册表中所有规则的元数据。"""
    from ontology_engine.rules.rule_updater import _get_registry
    registry = _get_registry()
    rules    = registry.get_ordered_rules()
    return [
        {
            "rule_id":             r.rule_id,
            "depends_on":          r.depends_on,
            "affected_properties": r.affected_properties,
            "class_name":          type(r).__name__,
        }
        for r in rules
    ]


@app.get("/health", summary="服务健康状态")
async def health() -> dict:
    """返回服务基础健康信息。"""
    user_count = 0
    try:
        if _BACKEND == "graphdb":
            from ontology_engine.core.graphdb_client import get_graphdb
            from ontology_engine.config.settings import ONTOLOGY_IRI
            ns   = ONTOLOGY_IRI.rstrip("#") + "#"
            rows = get_graphdb().sparql_select(
                f"SELECT (COUNT(?u) AS ?n) WHERE {{ ?u a <{ns}User> }}"
            )
            user_count = int(rows[0].get("n", 0)) if rows else 0
        else:
            from ontology_engine.core.ontology_registry import get_onto
            onto = get_onto()
            if hasattr(onto, "User"):
                user_count = len(list(onto.User.instances()))
    except Exception:
        pass

    return {
        "status":     "ok",
        "backend":    _BACKEND,
        "user_count": user_count,
    }
