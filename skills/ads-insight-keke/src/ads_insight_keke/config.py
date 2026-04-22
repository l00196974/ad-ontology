"""配置加载: settings.yaml / rss_feeds.conf / crawl_sources.conf。

使用方式:
    from ads_insight_keke.config import load_settings, load_feeds, load_crawl_sources

    s = load_settings()                        # 默认 config/settings.yaml
    feeds = load_feeds()                       # 默认 config/rss_feeds.conf
    sources = load_crawl_sources()             # 默认 config/crawl_sources.conf
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_SETTINGS = Path("config/settings.yaml")


@dataclass(frozen=True)
class Settings:
    database_path: str
    rss_workers: int
    crawl_workers: int
    llm_workers: int
    http_timeout: int
    http_retries: int
    user_agent: str
    max_articles_per_source: int
    link_score_threshold: int
    llm_timeout: int
    llm_max_retries: int
    log_level: str
    log_retain_days: int


def load_settings(path: Path | str = DEFAULT_SETTINGS) -> Settings:
    """加载 settings.yaml；缺失字段直接抛 KeyError 以 fail-fast。"""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return Settings(
        database_path=data["database"]["path"],
        rss_workers=int(data["concurrency"]["rss_workers"]),
        crawl_workers=int(data["concurrency"]["crawl_workers"]),
        llm_workers=int(data["concurrency"]["llm_workers"]),
        http_timeout=int(data["http"]["timeout_seconds"]),
        http_retries=int(data["http"]["retries"]),
        user_agent=str(data["http"]["user_agent"]),
        max_articles_per_source=int(data["crawler"]["max_articles_per_source"]),
        link_score_threshold=int(data["crawler"]["link_score_threshold"]),
        llm_timeout=int(data["llm"]["request_timeout"]),
        llm_max_retries=int(data["llm"]["max_retries"]),
        log_level=str(data["logging"]["level"]),
        log_retain_days=int(data["logging"]["retain_days"]),
    )


DEFAULT_FEEDS = Path("config/rss_feeds.conf")


@dataclass(frozen=True)
class FeedConfig:
    url: str
    label: str
    days: int
    categories: list[str]    # 小写; 空列表表示不过滤


def _parse_pipe_line(line: str, min_fields: int = 2) -> list[str] | None:
    """共享: 解析以 | 分隔的配置行, 返回去空白后的字段列表; None=应忽略。"""
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    parts = [p.strip() for p in line.split("|")]
    if len(parts) < min_fields or not parts[0]:
        return None
    return parts


def load_feeds(path: Path | str = DEFAULT_FEEDS) -> list[FeedConfig]:
    """解析 rss_feeds.conf。字段顺序: URL | 名称 | 过去N天(默认1) | category白名单。"""
    out: list[FeedConfig] = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        parts = _parse_pipe_line(raw, min_fields=2)
        if parts is None:
            continue
        url = parts[0]
        label = parts[1]
        days = int(parts[2]) if len(parts) >= 3 and parts[2] else 1
        cats_raw = parts[3] if len(parts) >= 4 else ""
        categories = [c.strip().lower() for c in cats_raw.split(",") if c.strip()]
        out.append(FeedConfig(url=url, label=label, days=days, categories=categories))
    return out


DEFAULT_CRAWL_SOURCES = Path("config/crawl_sources.conf")


@dataclass(frozen=True)
class CrawlConfig:
    url: str
    label: str
    days: int
    keywords: list[str]    # 小写; 空列表表示不过滤


def load_crawl_sources(path: Path | str = DEFAULT_CRAWL_SOURCES) -> list[CrawlConfig]:
    """解析 crawl_sources.conf。"""
    out: list[CrawlConfig] = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        parts = _parse_pipe_line(raw, min_fields=2)
        if parts is None:
            continue
        url = parts[0]
        label = parts[1]
        days = int(parts[2]) if len(parts) >= 3 and parts[2] else 1
        kw_raw = parts[3] if len(parts) >= 4 else ""
        keywords = [k.strip().lower() for k in kw_raw.split(",") if k.strip()]
        out.append(CrawlConfig(url=url, label=label, days=days, keywords=keywords))
    return out
