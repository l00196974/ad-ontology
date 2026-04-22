"""URL 可访问性校验: HEAD 主, GET 兜底, 重试 1 次。

调用方式:
    ok = await validate(client, "https://x.com/a", timeout=20)
"""
from __future__ import annotations

import logging

import httpx

log = logging.getLogger("url")


async def validate(client: httpx.AsyncClient, url: str, *, timeout: int = 20) -> bool:
    for attempt in (1, 2):
        try:
            r = await client.head(url, timeout=timeout, follow_redirects=True)
            if r.status_code < 400:
                return True
            # HEAD 被拒, 回落到 GET
            r = await client.get(url, timeout=timeout, follow_redirects=True)
            if r.status_code < 400:
                return True
            log.warning("URL 校验非 2xx/3xx (attempt %d): %s -> %d", attempt, url, r.status_code)
        except httpx.HTTPError as e:
            log.warning("URL 校验异常 (attempt %d): %s -> %s", attempt, url, e)
    return False
