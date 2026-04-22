"""Web 爬虫 (crawl4ai 两阶段): 列表页 → 文章页。

CLI: python -m ads_insight_keke.web_crawler
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

from . import date_extractor, link_extractor
from .config import CrawlConfig, load_crawl_sources, load_settings
from .logging_setup import setup_logging
from .models import Article

log = logging.getLogger("crawl")
OUT_FILE = Path("data/crawl_data.json")


def _meta_description(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for sel in [
        ("meta", {"name": "description"}),
        ("meta", {"property": "og:description"}),
    ]:
        tag = soup.find(*sel)
        if tag and tag.get("content"):
            return tag["content"].strip()
    return ""


def _title_from_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    og = soup.find("meta", attrs={"property": "og:title"})
    if og and og.get("content"):
        return og["content"].strip()
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    return ""


def _in_window(publish_date: str, days: int) -> bool:
    try:
        d = date.fromisoformat(publish_date)
    except ValueError:
        return False
    today = datetime.now(timezone.utc).date()
    return today - timedelta(days=days) <= d <= today


def _keyword_hits(text: str, keywords: list[str]) -> list[str]:
    if not keywords:
        return []
    low = text.lower()
    return [k for k in keywords if k.lower() in low]


async def _fetch_article(
    crawler: AsyncWebCrawler,
    url: str,
    source: CrawlConfig,
    stats: dict[str, int],
) -> Article | None:
    try:
        try:
            result = await crawler.arun(url=url, config=CrawlerRunConfig(word_count_threshold=200))
        except Exception as e:    # crawl4ai 内部异常种类多, 统一捕获
            log.warning("[%s] 抓取异常 %s: %s", source.label, url, e)
            stats["fetch_error"] += 1
            return None

        if not result or not getattr(result, "success", False):
            log.info("[%s] drop=fetch_failed %s", source.label, url)
            stats["fetch_failed"] += 1
            return None

        html = result.html or ""
        content = (result.markdown or "").strip() if hasattr(result, "markdown") else ""
        if not content and html:
            content = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
        title = _title_from_html(html)
        if not title:
            log.info("[%s] drop=no_title %s", source.label, url)
            stats["no_title"] += 1
            return None

        pub = await date_extractor.extract(
            html=html, url=url, content=content, title=title, allow_llm=False,
        )
        if not pub:
            log.info("[%s] drop=no_date %s", source.label, url)
            stats["no_date"] += 1
            return None
        if not _in_window(pub, source.days):
            log.info("[%s] drop=out_of_window date=%s days=%d %s",
                     source.label, pub, source.days, url)
            stats["out_of_window"] += 1
            return None

        tldr = (_meta_description(html) or content[:150]).strip()[:150]
        text_for_keyword = f"{title}\n{tldr}\n{content}"
        if source.keywords:
            hits = _keyword_hits(text_for_keyword, source.keywords)
            if not hits:
                log.info("[%s] drop=no_keyword_hit keywords=%s %s",
                         source.label, source.keywords, url)
                stats["no_keyword_hit"] += 1
                return None
        else:
            hits = []

        log.info("[%s] kept date=%s %s", source.label, pub, url)
        stats["kept"] += 1
        return Article(
            source_platform=source.label,
            title=title,
            original_url=url,
            publish_date=pub,
            tldr=tldr,
            content=content,
            picture_url="",
            category_or_keyword_hits=hits,
        )
    except Exception as e:
        log.warning("[%s] 单文章处理异常 %s: %s", source.label, url, e)
        stats["exception"] += 1
        return None


async def _crawl_one_source(
    crawler: AsyncWebCrawler,
    source: CrawlConfig,
    max_articles: int,
    threshold: int,
) -> list[Article]:
    try:
        listing = await crawler.arun(url=source.url)
    except Exception as e:
        log.error("[%s] 列表页抓取失败: %s", source.label, e)
        return []
    if not listing or not getattr(listing, "success", False):
        log.error("[%s] 列表页抓取失败 (无结果)", source.label)
        return []

    links = link_extractor.extract_article_links(
        listing.html or "", source.url, threshold=threshold, limit=max_articles,
    )
    log.info("[%s] 列表页链接=%d (阈值=%d)", source.label, len(links), threshold)
    for u in links:
        log.debug("[%s] 候选链接: %s", source.label, u)

    stats = {"kept": 0, "fetch_error": 0, "fetch_failed": 0,
             "no_title": 0, "no_date": 0, "out_of_window": 0,
             "no_keyword_hit": 0, "exception": 0}
    results = await asyncio.gather(
        *[_fetch_article(crawler, u, source, stats) for u in links],
        return_exceptions=True,
    )
    kept = [a for a in results if isinstance(a, Article)]
    log.info(
        "[%s] 总结: 链接=%d kept=%d fetch_error=%d fetch_failed=%d no_title=%d "
        "no_date=%d out_of_window=%d no_keyword_hit=%d exception=%d",
        source.label, len(links), stats["kept"], stats["fetch_error"],
        stats["fetch_failed"], stats["no_title"], stats["no_date"],
        stats["out_of_window"], stats["no_keyword_hit"], stats["exception"],
    )
    return kept


async def crawl_sources() -> int:
    settings = load_settings()
    sources = load_crawl_sources()

    browser_cfg = BrowserConfig(headless=True, user_agent=settings.user_agent)
    sem = asyncio.Semaphore(settings.crawl_workers)
    items: list[Article] = []

    async with AsyncWebCrawler(config=browser_cfg) as crawler:
        async def _worker(s: CrawlConfig) -> list[Article]:
            async with sem:
                return await _crawl_one_source(
                    crawler, s,
                    max_articles=settings.max_articles_per_source,
                    threshold=settings.link_score_threshold,
                )

        groups = await asyncio.gather(*[_worker(s) for s in sources])
        for g in groups:
            items.extend(g)

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    if OUT_FILE.exists():
        OUT_FILE.unlink()
    OUT_FILE.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "source_kind": "crawl",
        "count": len(items),
        "items": [a.model_dump() for a in items],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("爬虫采集完成: sources=%d total_items=%d -> %s", len(sources), len(items), OUT_FILE)
    return len(items)


def main() -> int:
    settings = load_settings()
    setup_logging("crawl", level=settings.log_level, retain_days=settings.log_retain_days)
    asyncio.run(crawl_sources())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
