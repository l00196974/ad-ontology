"""
__main__.py — 流水线入口

支持四种运行模式：
  1. 命令行模式（兼容旧版）：python __main__.py --urls URL1 URL2
  2. 配置文件模式：          python __main__.py --config crawl_tasks.yaml
  3. 两阶段模式（列表页发现）：配置文件中使用 listing_urls 字段
  4. 微信公众号模式：         配置文件中使用 engine: wechat + wechat_accounts

用法：
    python __main__.py                                    # 使用内置测试 URL（crawl4ai）
    python __main__.py --urls URL1 URL2                   # 自定义 URL 列表（crawl4ai）
    python __main__.py --config crawl_tasks.yaml          # YAML 配置，多引擎分发
    python __main__.py --config crawl_tasks.yaml --no-dedup  # 跳过去重
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

# ------------------------------------------------------------------ #
# 日志配置：必须在导入其他本地模块前设置，确保所有模块的 logger 继承格式  #
# ------------------------------------------------------------------ #
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stderr,  # 日志输出到 stderr，stdout 专用于结构化 JSON 结果
)

from base_fetcher import BaseFetcher      # noqa: E402
from config import CrawlTask, WechatOptions, load_config  # noqa: E402
from dedup import content_hash            # noqa: E402
from fetcher import Crawl4AiFetcher       # noqa: E402
from link_extractor import (              # noqa: E402
    extract_links_from_crawl4ai,
    extract_links_from_scrapling,
    filter_article_links,
    normalize_url,
)
from scrapling_fetcher import ScraplingFetcher  # noqa: E402
from storage import SQLiteStorage         # noqa: E402
from wechat_fetcher import WechatFetcher  # noqa: E402

log = logging.getLogger(__name__)

# 内置测试 URL：广告技术领域高质量内容源
_DEFAULT_TEST_URLS = [
    "https://adexchanger.com/ad-tech/what-is-programmatic-advertising/",
    "https://blog.google/products/ads/",
]

# 默认数据库路径：与 __main__.py 同目录
_DEFAULT_DB_PATH = Path(__file__).parent / "articles.db"


def _parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        description="Ad Insights Crawler — 多引擎本地抓取工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # --- 配置文件模式 ---
    parser.add_argument(
        "--config",
        default=None,
        metavar="PATH",
        help="YAML 配置文件路径（启用多引擎分发模式）",
    )
    parser.add_argument(
        "--no-dedup",
        action="store_true",
        default=False,
        help="跳过内容去重（默认启用去重）",
    )

    # --- 数据库路径（通用，优先级：CLI --db > YAML db_path > 默认值）---
    parser.add_argument(
        "--db",
        default=None,
        metavar="PATH",
        help="SQLite 数据库文件路径（覆盖 YAML 配置中的 db_path）",
    )

    # --- 命令行模式（兼容旧版）---
    parser.add_argument(
        "--urls",
        nargs="+",
        default=None,
        metavar="URL",
        help="待抓取的 URL 列表（默认使用内置测试 URL）",
    )
    parser.add_argument(
        "--concurrent",
        type=int,
        default=3,
        metavar="N",
        help="最大并发浏览器上下文数（默认：3）",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.48,
        metavar="FLOAT",
        help="PruningContentFilter 剪枝阈值 0~1（默认：0.48，越高过滤越激进）",
    )

    return parser.parse_args()


# --------------------------------------------------------------------------- #
# 引擎工厂                                                                       #
# --------------------------------------------------------------------------- #

def _create_fetcher(task: CrawlTask) -> BaseFetcher:
    """引擎工厂：根据任务配置创建对应的抓取引擎（用于列表页或直接 URL）。"""
    if task.engine == "crawl4ai":
        return Crawl4AiFetcher(
            pruning_threshold=task.options.threshold,
            page_timeout_ms=task.options.timeout * 1000,
            max_concurrent=task.options.concurrent,
        )
    elif task.engine == "scrapling":
        return ScraplingFetcher(
            fetcher_type=task.fetcher_type,
            timeout=task.options.timeout,
            max_concurrent=task.options.concurrent,
            headless=task.options.headless,
        )
    elif task.engine == "wechat":
        return _create_wechat_fetcher(task)
    else:
        raise ValueError(f"未知的引擎类型：{task.engine}")


def _create_wechat_fetcher(task: CrawlTask) -> WechatFetcher:
    """创建微信公众号引擎实例。"""
    cookie = os.environ.get("WECHAT_COOKIE", "")
    token = os.environ.get("WECHAT_TOKEN", "")
    if not cookie or not token:
        raise ValueError(
            "微信引擎需要设置 WECHAT_COOKIE 和 WECHAT_TOKEN 环境变量。\n"
            "获取方式：登录 https://mp.weixin.qq.com/ → 浏览器开发者工具 → "
            "Network → 找任意请求的 cookie 和 token 参数。"
        )
    opts = task.wechat_options or WechatOptions()
    return WechatFetcher(cookie=cookie, token=token, delay=opts.delay)


def _create_article_fetcher(task: CrawlTask) -> BaseFetcher:
    """创建文章内容抓取引擎（Phase 2），支持与列表页不同的引擎。"""
    engine = task.article_engine or task.engine
    options = task.article_options or task.options

    if engine == "crawl4ai":
        return Crawl4AiFetcher(
            pruning_threshold=options.threshold,
            page_timeout_ms=options.timeout * 1000,
            max_concurrent=options.concurrent,
        )
    elif engine == "scrapling":
        fetcher_type = task.article_fetcher_type if task.article_engine else task.fetcher_type
        return ScraplingFetcher(
            fetcher_type=fetcher_type,
            timeout=options.timeout,
            max_concurrent=options.concurrent,
            headless=options.headless,
        )
    elif engine == "wechat":
        return _create_wechat_fetcher(task)
    else:
        raise ValueError(f"未知的引擎类型：{engine}")


# --------------------------------------------------------------------------- #
# 两阶段抓取辅助函数                                                               #
# --------------------------------------------------------------------------- #

async def _extract_listing_links(fetcher, task: CrawlTask) -> list[str]:
    """Phase 1：从列表页提取文章链接。

    逐个抓取 listing_urls，提取链接并用启发式评分过滤，跨页去重。
    """
    all_article_urls = []
    seen_urls = set()

    for listing_url in task.listing_urls:
        log.info("Phase 1: 抓取列表页 [%s]", listing_url)

        try:
            raw_responses = await fetcher.fetch_raw([listing_url])
        except Exception as exc:
            log.error("列表页抓取失败 [%s]: %s", listing_url, exc)
            continue

        if not raw_responses:
            log.warning("列表页无有效响应 [%s]", listing_url)
            continue

        resp = raw_responses[0]

        # 根据引擎类型提取原始链接
        if task.engine == "crawl4ai":
            candidates = extract_links_from_crawl4ai(resp, listing_url)
        elif task.engine == "scrapling":
            candidates = extract_links_from_scrapling(resp, listing_url, task.link_selector)
        else:
            candidates = []

        log.info("列表页 [%s] 提取到 %d 个原始链接", listing_url, len(candidates))

        # 启发式过滤
        article_urls = filter_article_links(
            candidates, listing_url, task.max_articles, task.link_pattern,
        )

        # 跨列表页去重
        for url in article_urls:
            if url not in seen_urls:
                seen_urls.add(url)
                all_article_urls.append(url)

    return all_article_urls


def _merge_and_dedup_urls(direct_urls: list[str], discovered_urls: list[str]) -> list[str]:
    """合并直接 URL 和发现的 URL，保序去重（直接 URL 优先）。"""
    seen = set()
    result = []
    for url in direct_urls + discovered_urls:
        normalized = normalize_url(url, url)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _dedup_and_store(articles, storage, skip_dedup: bool) -> tuple[list, int]:
    """去重并存储文章，返回 (保存的文章列表, 存储条数)。"""
    if skip_dedup:
        for a in articles:
            a.content_hash = content_hash(a.content_markdown)
        saved_count = storage.upsert_batch(articles)
        return articles, saved_count
    else:
        new_articles = []
        for a in articles:
            h = content_hash(a.content_markdown)
            if storage.needs_update(a.url, h):
                a.content_hash = h
                new_articles.append(a)
            else:
                log.info("内容未变化，跳过 [%s]", a.url)
        saved_count = storage.upsert_batch(new_articles)
        return new_articles, saved_count


# --------------------------------------------------------------------------- #
# 摘要构建                                                                       #
# --------------------------------------------------------------------------- #

def _build_summary(articles) -> list[dict]:
    """构造摘要列表（不含全文，避免 stdout 过长）。"""
    return [
        {
            "url": a.url,
            "title": a.title,
            "author": a.author,
            "publish_date": a.publish_date,
            "cover_image_url": a.cover_image_url,
            "content_length_chars": len(a.content_markdown),
            "content_hash": a.content_hash,
            "crawl_time": a.crawl_time.isoformat(),
        }
        for a in articles
    ]


# --------------------------------------------------------------------------- #
# 配置文件模式                                                                    #
# --------------------------------------------------------------------------- #

async def run_config(config_path: str, skip_dedup: bool = False, db_path_override: str | None = None) -> list[dict]:
    """配置文件模式：执行所有任务组，支持多引擎分发、两阶段抓取和去重。

    Args:
        config_path: YAML 配置文件路径。
        skip_dedup: 是否跳过内容去重。
        db_path_override: CLI --db 指定的路径，覆盖 YAML 中的 db_path。
    """
    config = load_config(config_path)
    db_path = db_path_override or config.db_path
    log.info("数据库路径：%s%s", db_path, "（CLI 覆盖）" if db_path_override else "")
    storage = SQLiteStorage(db_path=db_path)
    all_saved = []

    try:
        for task in config.tasks:
            # ---- 微信公众号模式：独立的两阶段流程 ----
            if task.engine == "wechat" and task.wechat_accounts:
                log.info(
                    "任务组 [%s] 微信公众号模式：%d 个公众号",
                    task.name, len(task.wechat_accounts),
                )
                wechat_fetcher = _create_wechat_fetcher(task)
                opts = task.wechat_options or WechatOptions()

                # Phase 1: 从公众号后台 API 获取文章列表
                article_info_list = await wechat_fetcher.fetch_article_urls(
                    task.wechat_accounts,
                    count=opts.count,
                    max_pages=opts.max_pages,
                )
                article_urls = [item["link"] for item in article_info_list if item.get("link")]
                log.info(
                    "任务组 [%s] Phase 1 完成：发现 %d 篇文章 URL",
                    task.name, len(article_urls),
                )

                if not article_urls:
                    log.warning("任务组 [%s] 未获取到文章 URL，跳过", task.name)
                    continue

                # Phase 2: 抓取文章内容（可用 article_engine 覆盖）
                if task.article_engine and task.article_engine != "wechat":
                    article_fetcher = _create_article_fetcher(task)
                else:
                    article_fetcher = wechat_fetcher

                log.info(
                    "任务组 [%s] Phase 2：抓取 %d 篇文章内容",
                    task.name, len(article_urls),
                )
                articles = await article_fetcher.fetch_all(article_urls)

                # 去重 + 存储
                saved_articles, saved_count = _dedup_and_store(articles, storage, skip_dedup)
                all_saved.extend(saved_articles)
                log.info(
                    "任务组 [%s] 完成：发现 %d 个 URL，抓取 %d 篇，存储 %d 篇",
                    task.name, len(article_urls), len(articles), saved_count,
                )
                continue

            # ---- Phase 1：列表页发现文章链接 ----
            discovered_urls: list[str] = []
            if task.listing_urls:
                log.info(
                    "任务组 [%s] Phase 1：从 %d 个列表页提取文章链接（引擎=%s%s）",
                    task.name, len(task.listing_urls), task.engine,
                    f"/{task.fetcher_type}" if task.engine == "scrapling" else "",
                )
                listing_fetcher = _create_fetcher(task)
                discovered_urls = await _extract_listing_links(listing_fetcher, task)
                log.info(
                    "任务组 [%s] Phase 1 完成：发现 %d 个文章链接",
                    task.name, len(discovered_urls),
                )

            # ---- 合并直接 URL + 发现的 URL ----
            all_article_urls = _merge_and_dedup_urls(task.urls, discovered_urls)

            if not all_article_urls:
                log.warning("任务组 [%s] 无有效文章 URL，跳过", task.name)
                continue

            # ---- Phase 2：抓取文章内容 ----
            article_fetcher = _create_article_fetcher(task)
            article_engine = task.article_engine or task.engine
            log.info(
                "任务组 [%s] Phase 2：抓取 %d 篇文章内容（引擎=%s）",
                task.name, len(all_article_urls), article_engine,
            )
            articles = await article_fetcher.fetch_all(all_article_urls)

            # ---- 去重 + 存储 ----
            saved_articles, saved_count = _dedup_and_store(articles, storage, skip_dedup)
            all_saved.extend(saved_articles)

            log.info(
                "任务组 [%s] 完成：发现 %d 个 URL，抓取 %d 篇，存储 %d 篇",
                task.name, len(all_article_urls), len(articles), saved_count,
            )

    finally:
        storage.close()

    return _build_summary(all_saved)


# --------------------------------------------------------------------------- #
# 命令行模式（兼容旧版）                                                           #
# --------------------------------------------------------------------------- #

async def run_legacy(args: argparse.Namespace) -> list[dict]:
    """命令行模式（兼容旧版）：使用 crawl4ai 引擎。"""
    urls: list[str] = args.urls or _DEFAULT_TEST_URLS
    db_path = args.db or str(_DEFAULT_DB_PATH)

    log.info(
        "启动抓取流水线：%d 个 URL，并发数=%d，剪枝阈值=%.2f，数据库=%s",
        len(urls), args.concurrent, args.threshold, db_path,
    )

    fetcher = Crawl4AiFetcher(
        pruning_threshold=args.threshold,
        max_concurrent=args.concurrent,
    )
    storage = SQLiteStorage(db_path=db_path)

    try:
        articles = await fetcher.fetch_all(urls)
        saved_articles, saved_count = _dedup_and_store(articles, storage, args.no_dedup)

        log.info(
            "流水线完成：抓取成功 %d 条，存储成功 %d 条，共尝试 %d 个 URL",
            len(saved_articles), saved_count, len(urls),
        )
        return _build_summary(saved_articles)

    finally:
        storage.close()


# --------------------------------------------------------------------------- #
# 入口                                                                          #
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    args = _parse_args()

    if args.config:
        summary = asyncio.run(run_config(args.config, skip_dedup=args.no_dedup, db_path_override=args.db))
    else:
        summary = asyncio.run(run_legacy(args))

    # JSON 输出到 stdout
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    # 人类可读摘要到 stderr
    if summary:
        print("\n--- 抓取结果 ---", file=sys.stderr)
        for i, item in enumerate(summary, 1):
            print(f"  {i}. {item['title']}", file=sys.stderr)
            print(f"     URL: {item['url']}", file=sys.stderr)
            print(f"     正文长度: {item['content_length_chars']} 字符", file=sys.stderr)
    else:
        print("\n[警告] 所有 URL 均抓取失败或内容无变化。", file=sys.stderr)
