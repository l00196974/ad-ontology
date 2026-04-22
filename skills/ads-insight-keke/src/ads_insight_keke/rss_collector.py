"""RSS 采集器。

CLI: python -m ads_insight_keke.rss_collector

流程:
 1. 读 config/rss_feeds.conf
 2. asyncio.gather (rss_workers) 并发拉取每个 feed
 3. 每条 entry 依次做: 日期解析 → 时间窗判断 → category 白名单 → 字段抽取
 4. 写 data/rss_data.json (先删后写)
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import feedparser
import httpx
from bs4 import BeautifulSoup
from dateutil import parser as dtparser

from . import date_extractor
from .config import FeedConfig, load_feeds, load_settings
from .logging_setup import setup_logging
from .models import Article

log = logging.getLogger("rss")

OUT_FILE = Path("data/rss_data.json")
_DATE_KEY_RE = re.compile(r"(date|time)", re.IGNORECASE)


def _strip_html(s: str | None) -> str:
    if not s:
        return ""
    return BeautifulSoup(s, "html.parser").get_text(" ", strip=True)


def _extract_entry_text(entry: Any) -> str:
    if getattr(entry, "content", None):
        try:
            return _strip_html(entry.content[0].value)
        except (AttributeError, IndexError):
            pass
    return _strip_html(getattr(entry, "summary", "") or getattr(entry, "description", ""))


async def _resolve_date(entry: Any, title: str, content: str) -> str | None:
    """RSS 日期解析瀑布: 归一化字段 → 原始含 date/time 字段 → LLM 兜底。"""
    # 1) feedparser 归一化
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            try:
                return date(t.tm_year, t.tm_mon, t.tm_mday).isoformat()
            except (ValueError, TypeError):
                pass
    # 2) 遍历所有含 date/time 的键
    for k, v in entry.items():
        if not isinstance(v, str):
            continue
        if not _DATE_KEY_RE.search(k):
            continue
        try:
            return dtparser.parse(v, fuzzy=True).date().isoformat()
        except (ValueError, OverflowError, TypeError):
            continue
    # 3) LLM 兜底
    return await date_extractor.extract_via_llm(title, content)


def _categories_hit(entry: Any, whitelist: list[str]) -> list[str]:
    """返回命中的 category (小写); whitelist 为空时返回空 list (不过滤)。"""
    if not whitelist:
        return []
    tags = [t.term.lower() for t in getattr(entry, "tags", []) if getattr(t, "term", None)]
    hits = [t for t in tags if t in whitelist]
    return hits


def _in_window(publish_date: str, days: int) -> bool:
    try:
        d = date.fromisoformat(publish_date)
    except ValueError:
        return False
    today = datetime.now(timezone.utc).date()
    return today - timedelta(days=days) <= d <= today


async def _fetch_feed(client: httpx.AsyncClient, feed: FeedConfig) -> list[Article]:
    try:
        r = await client.get(feed.url, timeout=20.0, follow_redirects=True)
        r.raise_for_status()
    except httpx.HTTPError as e:
        log.error("[%s] 拉取失败: %s", feed.label, e)
        return []

    parsed = feedparser.parse(r.text)
    fetched = len(parsed.entries)
    articles: list[Article] = []
    dropped_no_date = 0
    dropped_window = 0
    dropped_category = 0

    for entry in parsed.entries:
        title = _strip_html(getattr(entry, "title", "")).strip()
        link = getattr(entry, "link", "").strip()
        if not title or not link:
            continue

        content = _extract_entry_text(entry)
        pub = await _resolve_date(entry, title, content)
        if not pub:
            dropped_no_date += 1
            continue
        if not _in_window(pub, feed.days):
            dropped_window += 1
            continue
        if feed.categories:
            hits = _categories_hit(entry, feed.categories)
            if not hits:
                dropped_category += 1
                continue
        else:
            hits = []

        summary = _strip_html(getattr(entry, "summary", "") or getattr(entry, "description", ""))
        tldr = (summary or content)[:150]
        articles.append(Article(
            source_platform=feed.label,
            title=title,
            original_url=link,
            publish_date=pub,
            tldr=tldr,
            content=content,
            picture_url="",
            category_or_keyword_hits=hits,
        ))

    log.info(
        "[%s] fetched=%d after_date=%d after_window=%d after_category=%d kept=%d",
        feed.label, fetched,
        fetched - dropped_no_date,
        fetched - dropped_no_date - dropped_window,
        fetched - dropped_no_date - dropped_window - dropped_category,
        len(articles),
    )
    return articles


async def collect_rss() -> int:
    settings = load_settings()
    feeds = load_feeds()
    sem = asyncio.Semaphore(settings.rss_workers)

    async with httpx.AsyncClient(headers={"User-Agent": settings.user_agent}) as client:
        async def _worker(f: FeedConfig) -> list[Article]:
            async with sem:
                return await _fetch_feed(client, f)

        results = await asyncio.gather(*[_worker(f) for f in feeds])

    items = [a.model_dump() for group in results for a in group]
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    if OUT_FILE.exists():
        OUT_FILE.unlink()
    OUT_FILE.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "source_kind": "rss",
        "count": len(items),
        "items": items,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("RSS 采集完成: feeds=%d total_items=%d -> %s", len(feeds), len(items), OUT_FILE)
    return len(items)


def main() -> int:
    settings = load_settings()
    setup_logging("rss", level=settings.log_level, retain_days=settings.log_retain_days)
    return 0 if asyncio.run(collect_rss()) >= 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
