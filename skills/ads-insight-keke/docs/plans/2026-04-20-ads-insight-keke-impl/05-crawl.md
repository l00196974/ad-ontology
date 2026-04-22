# 模块 05 · Web Crawler

基于 crawl4ai 两阶段抓取: 列表页 → 文章页。

---

### Task 5.1: link_extractor (启发式评分)

**Files:**
- Create: `skills/ads-insight-keke/src/ads_insight_keke/link_extractor.py`
- Create: `skills/ads-insight-keke/tests/test_link_extractor.py`

参考老工程 `python/link_extractor.py` 的评分思路, 但实现独立。

- [ ] **Step 1: 失败测试**

```python
from ads_insight_keke.link_extractor import score_link, extract_article_links


def test_article_path_scores_high() -> None:
    s = score_link("https://blog.x.com/2026/04/19/some-long-slug-title", "https://blog.x.com/")
    assert s >= 2


def test_pagination_scores_low() -> None:
    s = score_link("https://blog.x.com/posts?page=2", "https://blog.x.com/")
    assert s < 2


def test_external_filtered() -> None:
    s = score_link("https://other.com/whatever", "https://blog.x.com/")
    assert s < 0


def test_extract_picks_top_n() -> None:
    html = '<a href="/2026/04/19/post-a">A</a><a href="/page/2">B</a>'
    links = extract_article_links(html, "https://blog.x.com/listing", threshold=2, limit=5)
    assert any("post-a" in u for u in links)
    assert all("/page/" not in u for u in links)
```

- [ ] **Step 2: 实现**

```python
"""列表页文章链接提取: 启发式评分 + 阈值过滤。"""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from .id_gen import normalize_url

_DATE_PATH = re.compile(r"/\d{4}/\d{1,2}/")
_NUM_ID = re.compile(r"/\d{5,}")
_ARTICLE_HINTS = re.compile(r"/(p|post|article|news|blog)/")
_FILE_EXT = re.compile(r"\.(jpg|jpeg|png|gif|svg|webp|pdf|zip|mp4|mp3|css|js)(\?|$)", re.IGNORECASE)
_PAGINATION = re.compile(r"[?&](page|sort|filter|tag|category)=", re.IGNORECASE)


def _same_host(url: str, base: str) -> bool:
    return urlsplit(url).hostname == urlsplit(base).hostname


def score_link(url: str, base: str) -> int:
    if _FILE_EXT.search(url) or url.startswith(("mailto:", "javascript:")):
        return -10
    if not _same_host(url, base):
        return -10

    score = 0
    path = urlsplit(url).path
    depth = sum(1 for p in path.split("/") if p)
    if _NUM_ID.search(path):
        score += 3
    if _ARTICLE_HINTS.search(path):
        score += 2
    if _DATE_PATH.search(path):
        score += 3
    if depth >= 3:
        score += 2
    elif depth <= 1:
        score -= 2
    if "-" in path and len(path) > 12:
        score += 1
    if _PAGINATION.search(url):
        score -= 3
    return score


def extract_article_links(html: str, base_url: str, *, threshold: int = 2, limit: int = 30) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    scored: list[tuple[int, str]] = []
    for a in soup.find_all("a", href=True):
        absurl = urljoin(base_url, a["href"].strip())
        if not absurl.startswith(("http://", "https://")):
            continue
        norm = normalize_url(absurl)
        if norm in seen:
            continue
        s = score_link(absurl, base_url)
        if s >= threshold:
            seen.add(norm)
            scored.append((s, absurl))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [u for _, u in scored[:limit]]
```

- [ ] **Step 3: 测试 + commit**

```bash
pytest tests/test_link_extractor.py -v
git add skills/ads-insight-keke/{src/ads_insight_keke/link_extractor.py,tests/test_link_extractor.py}
git commit -m "feat(crawl): link_extractor 启发式文章链接提取"
```

---

### Task 5.2: web_crawler 主体

**Files:**
- Create: `skills/ads-insight-keke/src/ads_insight_keke/web_crawler.py`

- [ ] **Step 1: 实现**

```python
"""Web 爬虫 (crawl4ai 两阶段): 列表页 → 文章页。

CLI: python -m ads_insight_keke.web_crawler
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

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
    return [k for k in keywords if k in low]


async def _fetch_article(
    crawler: AsyncWebCrawler,
    url: str,
    source: CrawlConfig,
) -> Article | None:
    try:
        result = await crawler.arun(url=url, config=CrawlerRunConfig(word_count_threshold=200))
    except Exception as e:    # crawl4ai 内部异常种类多, 统一捕获
        log.warning("[%s] 抓取异常 %s: %s", source.label, url, e)
        return None

    if not result or not getattr(result, "success", False):
        log.warning("[%s] 抓取失败 %s", source.label, url)
        return None

    html = result.html or ""
    content = (result.markdown or "").strip() if hasattr(result, "markdown") else ""
    if not content and html:
        content = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    title = _title_from_html(html)
    if not title:
        return None

    pub = await date_extractor.extract(html=html, url=url, content=content, title=title)
    if not pub:
        log.debug("[%s] 无日期 %s", source.label, url)
        return None
    if not _in_window(pub, source.days):
        return None

    tldr = (_meta_description(html) or content[:150]).strip()[:150]
    text_for_keyword = f"{title}\n{tldr}\n{content}"
    if source.keywords:
        hits = _keyword_hits(text_for_keyword, source.keywords)
        if not hits:
            return None
    else:
        hits = []

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
    log.info("[%s] 列表页链接=%d", source.label, len(links))

    results = await asyncio.gather(*[_fetch_article(crawler, u, source) for u in links])
    kept = [a for a in results if a is not None]
    log.info("[%s] 抓取成功=%d 过滤后=%d", source.label, sum(1 for r in results if r), len(kept))
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
```

- [ ] **Step 2: commit**

```bash
git add skills/ads-insight-keke/src/ads_insight_keke/web_crawler.py
git commit -m "feat(crawl): web_crawler 两阶段抓取"
```

---

### Task 5.3: 脚本 run_crawl

**Files:**
- Create: `skills/ads-insight-keke/scripts/run_crawl.sh`
- Create: `skills/ads-insight-keke/scripts/run_crawl.ps1`

- [ ] **Step 1: run_crawl.sh**

```bash
#!/usr/bin/env bash
source "$(dirname "$0")/_common.sh"
LOG="logs/$(date +%F)-crawl.tee.log"
python -m ads_insight_keke.web_crawler 2>&1 | tee -a "$LOG"
exit ${PIPESTATUS[0]}
```

- [ ] **Step 2: run_crawl.ps1**

```powershell
. (Join-Path $PSScriptRoot "_common.ps1")
$log = Join-Path "logs" ("{0:yyyy-MM-dd}-crawl.tee.log" -f (Get-Date))
python -m ads_insight_keke.web_crawler 2>&1 | Tee-Object -Append -FilePath $log
exit $LASTEXITCODE
```

- [ ] **Step 3: chmod + commit**

```bash
chmod +x skills/ads-insight-keke/scripts/run_crawl.sh
git add skills/ads-insight-keke/scripts/run_crawl.sh skills/ads-insight-keke/scripts/run_crawl.ps1
git commit -m "feat(crawl): run_crawl 脚本"
```
