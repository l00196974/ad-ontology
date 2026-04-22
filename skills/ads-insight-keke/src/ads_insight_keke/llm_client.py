"""OpenAI 兼容 LLM 客户端封装。

环境变量:
    LLM_BASE_URL / LLM_API_KEY / LLM_MODEL
    ADS_INSIGHT_FAKE_LLM=1  -> 返回固定 JSON, 不发请求 (本地无 key 调试)

call_json(prompt, task) -> dict, 失败抛异常。
task 取值用于 FAKE 分支返回不同结构 (enrich / date)。
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from openai import AsyncOpenAI, APIError

log = logging.getLogger("llm")

_client: AsyncOpenAI | None = None
_client_lock = asyncio.Lock()


async def _get_client() -> AsyncOpenAI:
    """懒加载模块级单例 AsyncOpenAI 客户端，避免每次调用新建连接池。"""
    global _client
    if _client is None:                          # 快速路径（无锁）
        async with _client_lock:
            if _client is None:                  # 防竞争（锁内）
                base_url = os.environ.get("LLM_BASE_URL", "")
                api_key = os.environ.get("LLM_API_KEY", "")
                timeout = int(os.environ.get("LLM_TIMEOUT", "60"))
                _client = AsyncOpenAI(base_url=base_url, api_key=api_key, timeout=timeout)
    return _client


async def aclose() -> None:
    """关闭单例客户端，释放连接池。供测试或 pipeline main 结束时显式调用。"""
    global _client
    async with _client_lock:
        if _client is not None:
            await _client.close()
            _client = None

_FAKE_RESPONSES: dict[str, dict[str, Any]] = {
    "enrich": {
        "thoughts": "（FAKE）建议关注此方向的工程化落地与广告平台能力对齐，重点评估对召回/出价/创意流水线的影响。",
        "insight_type": "技术架构与算法",
        "tags": ["AIGC", "Google", "智能创意"],
    },
    "date": {"publish_date": "2026-04-19"},
}


def _is_fake() -> bool:
    return os.environ.get("ADS_INSIGHT_FAKE_LLM") == "1"


async def call_json(
    prompt: str,
    *,
    task: str,
    timeout: int = 60,
    max_retries: int = 2,
) -> dict[str, Any]:
    """调用 LLM 返回 JSON 对象。失败抛 RuntimeError。"""
    if _is_fake():
        log.debug("FAKE LLM (task=%s)", task)
        return dict(_FAKE_RESPONSES.get(task, {}))

    base_url = os.environ.get("LLM_BASE_URL", "")
    api_key = os.environ.get("LLM_API_KEY", "")
    model = os.environ.get("LLM_MODEL", "")
    if not (base_url and api_key and model):
        raise RuntimeError("LLM_BASE_URL / LLM_API_KEY / LLM_MODEL 未配置")

    client = await _get_client()
    last_err: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            r = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            text = r.choices[0].message.content or ""
            return json.loads(text)
        except (json.JSONDecodeError, APIError) as e:
            last_err = e
            log.warning("LLM 调用失败 task=%s attempt=%d err=%s", task, attempt, e)
    raise RuntimeError(f"LLM 调用最终失败: {last_err}")
