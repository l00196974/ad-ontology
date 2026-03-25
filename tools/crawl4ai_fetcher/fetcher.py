"""
fetcher.py — crawl4ai 抓取引擎

封装 crawl4ai AsyncWebCrawler，实现并发异步抓取和内容清洗。
替换抓取引擎（如换用 Scrapling、Playwright 原生）时，只需替换此文件，
models.py 和 storage.py 无需改动。
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

from base_fetcher import BaseFetcher
from models import ArticleInsight

logger = logging.getLogger(__name__)

# 最短有效正文字符数，低于此值视为抓取失败
_MIN_CONTENT_LENGTH = 100


class Crawl4AiFetcher(BaseFetcher):
    """基于 crawl4ai AsyncWebCrawler 的异步批量抓取器。

    Args:
        pruning_threshold: PruningContentFilter 剪枝阈值（0~1），越高过滤越激进。
                           默认 0.3，可降至 0.2 应对内容较少的页面。
        page_timeout_ms:   单页超时（毫秒），默认 30 秒。
        max_concurrent:    最大并发浏览器上下文数，默认 3，防止触发反爬限速。
    """

    def __init__(
        self,
        pruning_threshold: float = 0.3,
        page_timeout_ms: int = 30_000,
        max_concurrent: int = 3,
    ) -> None:
        # 浏览器级配置：headless 模式 + 真实 User-Agent（降低 403 概率）
        self._browser_config = BrowserConfig(
            headless=True,
            verbose=False,
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
        )

        # 内容过滤器：统计式剪枝，自动移除导航栏/侧边栏/广告/底部等低密度区块
        content_filter = PruningContentFilter(
            threshold=pruning_threshold,
            threshold_type="fixed",
            min_word_threshold=10,   # 少于 10 个词的 DOM 块直接丢弃
        )

        # Markdown 生成器：忽略图片（使用 og:image 替代），保留链接，不折行
        md_generator = DefaultMarkdownGenerator(
            content_filter=content_filter,
            options={
                "ignore_links": False,
                "ignore_images": True,
                "body_width": 0,
            },
        )

        # 每次抓取运行的配置：生成器 + 超时 + 不缓存
        # 注意：不使用 css_selector（会导致 <head> 中的 meta 标签无法被提取）
        # 注意：override_navigator / magic / simulate_user 在 crawl4ai 0.8.x
        #       存在 JS 表达式兼容问题，暂不启用
        self._run_config = CrawlerRunConfig(
            markdown_generator=md_generator,
            excluded_tags=[
                "nav", "footer", "header", "aside",
            ],
            wait_for_images=False,
            page_timeout=page_timeout_ms,
            cache_mode=CacheMode.BYPASS,    # 每次强制重新抓取，不使用磁盘缓存
            verbose=False,
        )

        # 信号量：控制同时打开的浏览器上下文数量
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def fetch_all(self, urls: list[str]) -> list[ArticleInsight]:
        """并发抓取 URL 列表，返回成功解析的 ArticleInsight 列表。

        失败的 URL 会被跳过（记录日志），不会抛出异常。
        """
        async with AsyncWebCrawler(config=self._browser_config) as crawler:
            tasks = [self._fetch_one_impl(crawler, url) for url in urls]
            outcomes = await asyncio.gather(*tasks)

        results = [r for r in outcomes if r is not None]
        logger.info("抓取完成：%d/%d 条成功", len(results), len(urls))
        return results

    async def fetch_one(self, url: str) -> Optional[ArticleInsight]:
        """抓取单个 URL（自建 crawler context），失败返回 None。"""
        async with AsyncWebCrawler(config=self._browser_config) as crawler:
            return await self._fetch_one_impl(crawler, url)

    async def _fetch_one_impl(
        self, crawler: AsyncWebCrawler, url: str
    ) -> Optional[ArticleInsight]:
        """抓取单个 URL 的内部实现，是每条 URL 的独立错误边界。"""
        async with self._semaphore:
            try:
                result = await crawler.arun(url=url, config=self._run_config)

                # crawl4ai 报告抓取失败（如网络错误、JS 执行异常）
                if not result.success:
                    logger.warning(
                        "crawl4ai 报告失败 [%s]: %s", url, result.error_message
                    )
                    return None

                # 提取 fit_markdown（经过 PruningContentFilter 过滤后的正文）
                md_obj = result.markdown
                # crawl4ai 0.4+ 返回 MarkdownGenerationResult 对象；兼容纯字符串场景
                # fit_markdown 是经过 PruningContentFilter 过滤后的正文；
                # 若过滤过于激进导致为空或过短，回退到 raw_markdown 保证内容不丢失
                if hasattr(md_obj, "fit_markdown"):
                    fit = md_obj.fit_markdown or ""
                    raw = md_obj.raw_markdown or ""
                    # fit_markdown 不到 raw 的 10% 时，说明剪枝过度，回退到 raw
                    if len(fit) < _MIN_CONTENT_LENGTH or (raw and len(fit) < len(raw) * 0.1):
                        md_text = raw
                        if fit:
                            logger.info(
                                "fit_markdown 过短（%d 字符 vs raw %d），回退到 raw_markdown [%s]",
                                len(fit), len(raw), url,
                            )
                    else:
                        md_text = fit
                else:
                    md_text = str(md_obj) if md_obj else ""

                # 正文过短说明抓取结果无意义（可能是 JS 渲染失败或内容在 paywall 后）
                if len(md_text.strip()) < _MIN_CONTENT_LENGTH:
                    logger.warning(
                        "正文过短，跳过 [%s]（%d 字符，阈值 %d）",
                        url, len(md_text.strip()), _MIN_CONTENT_LENGTH,
                    )
                    return None

                # 从页面 meta 标签中提取元数据
                meta: dict = result.metadata or {}
                title = (
                    meta.get("og:title")
                    or meta.get("title")
                    or url  # 兜底：用 URL 本身作为标题
                )
                author = meta.get("author") or meta.get("article:author")
                publish_date = (
                    meta.get("article:published_time")
                    or meta.get("datePublished")
                    or meta.get("date")
                )
                # 封面图：优先 og:image，其次 twitter:image
                cover_image_url = (
                    meta.get("og:image") or meta.get("twitter:image")
                )

                return ArticleInsight(
                    url=url,
                    title=title,
                    author=author,
                    publish_date=publish_date,
                    cover_image_url=cover_image_url,
                    content_markdown=md_text,
                    crawl_time=datetime.now(tz=timezone.utc),
                )

            except TimeoutError:
                # 页面加载超时（page_timeout 触发）
                logger.error("抓取超时，跳过 [%s]", url)
                return None
            except Exception as exc:
                # 捕获所有其他异常：HTTP 403/404、Playwright 崩溃、解析错误等
                msg = str(exc)
                if "403" in msg:
                    logger.error("HTTP 403 Forbidden，跳过 [%s]", url)
                elif "404" in msg:
                    logger.error("HTTP 404 Not Found，跳过 [%s]", url)
                else:
                    logger.error("未知错误，跳过 [%s]: %s", url, exc)
                return None
