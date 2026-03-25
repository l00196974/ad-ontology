"""
__main__.py — 流水线入口

支持两种运行模式：
  1. 命令行模式（兼容旧版）：python __main__.py --urls URL1 URL2
  2. 配置文件模式（新）：    python __main__.py --config crawl_tasks.yaml

配置文件模式支持多引擎分发和内容去重。

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
from config import CrawlTask, load_config # noqa: E402
from dedup import content_hash            # noqa: E402
from fetcher import Crawl4AiFetcher       # noqa: E402
from scrapling_fetcher import ScraplingFetcher  # noqa: E402
from storage import SQLiteStorage         # noqa: E402

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

    # --- 命令行模式（兼容旧版）---
    parser.add_argument(
        "--urls",
        nargs="+",
        default=None,
        metavar="URL",
        help="待抓取的 URL 列表（默认使用内置测试 URL）",
    )
    parser.add_argument(
        "--db",
        default=str(_DEFAULT_DB_PATH),
        metavar="PATH",
        help=f"SQLite 数据库文件路径（默认：{_DEFAULT_DB_PATH}）",
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


def _create_fetcher(task: CrawlTask) -> BaseFetcher:
    """引擎工厂：根据任务配置创建对应的抓取引擎。"""
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
    else:
        raise ValueError(f"未知的引擎类型：{task.engine}")


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


async def run_config(config_path: str, skip_dedup: bool = False) -> list[dict]:
    """配置文件模式：执行所有任务组，支持多引擎分发和去重。"""
    config = load_config(config_path)
    storage = SQLiteStorage(db_path=config.db_path)
    all_saved = []

    try:
        for task in config.tasks:
            log.info(
                "执行任务组 [%s]：引擎=%s%s，%d 个 URL",
                task.name, task.engine,
                f"/{task.fetcher_type}" if task.engine == "scrapling" else "",
                len(task.urls),
            )

            fetcher = _create_fetcher(task)
            articles = await fetcher.fetch_all(task.urls)

            if skip_dedup:
                # 跳过去重，直接存储
                for a in articles:
                    a.content_hash = content_hash(a.content_markdown)
                saved_count = storage.upsert_batch(articles)
                all_saved.extend(articles)
            else:
                # 去重：只存储内容有变化的文章
                new_articles = []
                for a in articles:
                    h = content_hash(a.content_markdown)
                    if storage.needs_update(a.url, h):
                        a.content_hash = h
                        new_articles.append(a)
                    else:
                        log.info("内容未变化，跳过 [%s]", a.url)

                saved_count = storage.upsert_batch(new_articles)
                all_saved.extend(new_articles)

            log.info(
                "任务组 [%s] 完成：抓取 %d 条，存储 %d 条",
                task.name, len(articles), saved_count,
            )

    finally:
        storage.close()

    return _build_summary(all_saved)


async def run_legacy(args: argparse.Namespace) -> list[dict]:
    """命令行模式（兼容旧版）：使用 crawl4ai 引擎。"""
    urls: list[str] = args.urls or _DEFAULT_TEST_URLS

    log.info(
        "启动抓取流水线：%d 个 URL，并发数=%d，剪枝阈值=%.2f，数据库=%s",
        len(urls), args.concurrent, args.threshold, args.db,
    )

    fetcher = Crawl4AiFetcher(
        pruning_threshold=args.threshold,
        max_concurrent=args.concurrent,
    )
    storage = SQLiteStorage(db_path=args.db)

    try:
        articles = await fetcher.fetch_all(urls)

        # 去重
        if not args.no_dedup:
            new_articles = []
            for a in articles:
                h = content_hash(a.content_markdown)
                if storage.needs_update(a.url, h):
                    a.content_hash = h
                    new_articles.append(a)
                else:
                    log.info("内容未变化，跳过 [%s]", a.url)
            saved_count = storage.upsert_batch(new_articles)
            articles = new_articles
        else:
            for a in articles:
                a.content_hash = content_hash(a.content_markdown)
            saved_count = storage.upsert_batch(articles)

        log.info(
            "流水线完成：抓取成功 %d 条，存储成功 %d 条，共尝试 %d 个 URL",
            len(articles), saved_count, len(urls),
        )
        return _build_summary(articles)

    finally:
        storage.close()


if __name__ == "__main__":
    args = _parse_args()

    if args.config:
        # 配置文件模式
        summary = asyncio.run(run_config(args.config, skip_dedup=args.no_dedup))
    else:
        # 命令行模式（兼容旧版）
        summary = asyncio.run(run_legacy(args))

    # 将结果以 JSON 格式输出到 stdout（方便管道传递给下游工具）
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    # 在控制台额外打印人类可读的标题列表（方便快速核验）
    if summary:
        print("\n--- 抓取结果 ---", file=sys.stderr)
        for i, item in enumerate(summary, 1):
            print(f"  {i}. {item['title']}", file=sys.stderr)
            print(f"     URL: {item['url']}", file=sys.stderr)
            print(f"     正文长度: {item['content_length_chars']} 字符", file=sys.stderr)
    else:
        print("\n[警告] 所有 URL 均抓取失败或内容无变化。", file=sys.stderr)
