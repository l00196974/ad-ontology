"""Exa.ai 语义检索采集器。

CLI: python -m ads_insight_keke.exa_collector

流程:
 1. 读 config/exa_sources.conf
 2. asyncio.gather (exa_workers) 并发执行每条 query
 3. 每条结果做: 字段映射 → 日期窗口判断 → 字段抽取
 4. 写 data/exa_data.json (先删后写)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx

from .config import ExaConfig, load_exa_sources, load_settings
from .logging_setup import setup_logging
from .models import Article
from .text_utils import normalize_tldr

log = logging.getLogger("exa")
OUT_FILE = Path("data/exa_data.json")
EXA_API_URL = "https://api.exa.ai/search"


def _in_window(publish_date: str, days: int) -> bool:
    try:
        d = date.fromisoformat(publish_date)
    except ValueError:
        return False
    today = datetime.now(timezone.utc).date()
    return today - timedelta(days=days) <= d <= today


def _parse_date(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        return raw[:10]
    except Exception:
        return None


async def _search_one(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    source: ExaConfig,
    api_key: str,
) -> list[Article]:
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=source.days)
    body: dict = {
        "query": source.query,
        "type": "auto",
        "numResults": 20,
        "startPublishedDate": f"{start.isoformat()}T00:00:00Z",
        "endPublishedDate": f"{today.isoformat()}T23:59:59Z",
        "contents": {
            "text": {"maxCharacters": 5000},
            "summary": True,
            "highlights": {"maxCharacters": 500},
        },
    }
    if source.include_domains:
        body["includeDomains"] = source.include_domains
    if source.exclude_domains:
        body["excludeDomains"] = source.exclude_domains

    stats = {"kept": 0, "no_title": 0, "no_date": 0, "out_of_window": 0}

    async with sem:
        try:
            resp = await client.post(
                EXA_API_URL,
                headers={"x-api-key": api_key, "Content-Type": "application/json"},
                json=body,
                timeout=60,
            )
            resp.raise_for_status()
        except Exception as e:
            log.error("[%s] Exa API 请求失败: %s", source.label, e)
            return []

    data = resp.json()
    results = data.get("results", [])
    log.info("[%s] Exa 返回 %d 条结果", source.label, len(results))

    articles: list[Article] = []
    for r in results:
        title = (r.get("title") or "").strip()
        if not title:
            stats["no_title"] += 1
            continue

        url = (r.get("url") or "").strip()
        if not url:
            continue

        pub = _parse_date(r.get("publishedDate"))
        if not pub:
            log.info("[%s] drop=no_date %s", source.label, url)
            stats["no_date"] += 1
            continue
        if not _in_window(pub, source.days):
            log.info("[%s] drop=out_of_window date=%s days=%d %s",
                     source.label, pub, source.days, url)
            stats["out_of_window"] += 1
            continue

        text = (r.get("text") or "").strip()
        summary = (r.get("summary") or "").strip()
        highlights = " ".join(r.get("highlights") or []).strip()
        tldr = normalize_tldr(summary or highlights or text)

        stats["kept"] += 1
        articles.append(Article(
            source_platform=source.label,
            title=title,
            original_url=url,
            publish_date=pub,
            tldr=tldr,
            content=text,
            picture_url="",
            category_or_keyword_hits=[],
        ))

    log.info("[%s] 总结: results=%d kept=%d no_title=%d no_date=%d out_of_window=%d",
             source.label, len(results), stats["kept"],
             stats["no_title"], stats["no_date"], stats["out_of_window"])
    return articles


# --- PLACEHOLDER_COLLECT_EXA ---


async def collect_exa() -> int:
    settings = load_settings()
    sources = load_exa_sources()
    api_key = os.environ.get("EXA_API_KEY", "").strip()
    if not api_key:
        log.warning("EXA_API_KEY 未配置, 跳过 Exa 采集")
        return 0
    if not sources:
        log.warning("exa_sources.conf 为空, 跳过 Exa 采集")
        return 0

    sem = asyncio.Semaphore(settings.exa_workers)
    items: list[Article] = []

    async with httpx.AsyncClient(headers={"User-Agent": settings.user_agent}) as client:
        groups = await asyncio.gather(
            *[_search_one(client, sem, s, api_key) for s in sources],
            return_exceptions=True,
        )
        for g in groups:
            if isinstance(g, BaseException):
                log.warning("Exa 查询异常: %s", g)
            else:
                items.extend(g)

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    if OUT_FILE.exists():
        OUT_FILE.unlink()
    OUT_FILE.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "source_kind": "exa",
        "count": len(items),
        "items": [a.model_dump() for a in items],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Exa 采集完成: sources=%d total_items=%d -> %s", len(sources), len(items), OUT_FILE)
    return len(items)


def main() -> int:
    settings = load_settings()
    setup_logging("exa", level=settings.log_level, retain_days=settings.log_retain_days)
    asyncio.run(collect_exa())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
