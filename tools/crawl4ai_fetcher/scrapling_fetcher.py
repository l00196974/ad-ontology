"""
scrapling_fetcher.py — Scrapling 抓取引擎

支持三种 Scrapling 子引擎：
  - async:    AsyncFetcher（轻量 HTTP，不渲染 JS，速度最快）
  - stealthy: StealthyFetcher（Camoufox 反爬浏览器，渲染 JS，可绕 Cloudflare）
  - dynamic:  DynamicFetcher（Playwright 浏览器，渲染 JS）

替换或新增抓取引擎时，只需实现 BaseFetcher 接口。
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Literal, Optional

from markdownify import markdownify as md

from base_fetcher import BaseFetcher
from models import ArticleInsight

logger = logging.getLogger(__name__)

# 最短有效正文字符数
_MIN_CONTENT_LENGTH = 100


class ScraplingFetcher(BaseFetcher):
    """基于 Scrapling 的多引擎抓取器。

    Args:
        fetcher_type:   引擎类型：async / stealthy / dynamic。
        timeout:        请求超时（秒），stealthy/dynamic 内部自动转为毫秒。
        max_concurrent: 最大并发数。
        headless:       是否无头模式（仅 stealthy / dynamic 有效）。
    """

    def __init__(
        self,
        fetcher_type: Literal["async", "stealthy", "dynamic"] = "async",
        timeout: int = 30,
        max_concurrent: int = 3,
        headless: bool = True,
    ) -> None:
        self._fetcher_type = fetcher_type
        self._timeout = timeout
        self._headless = headless
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def fetch_all(self, urls: list[str]) -> list[ArticleInsight]:
        """并发抓取 URL 列表。"""
        tasks = [self.fetch_one(url) for url in urls]
        outcomes = await asyncio.gather(*tasks)
        results = [r for r in outcomes if r is not None]
        logger.info(
            "Scrapling[%s] 抓取完成：%d/%d 条成功",
            self._fetcher_type, len(results), len(urls),
        )
        return results

    async def fetch_one(self, url: str) -> Optional[ArticleInsight]:
        """抓取单个 URL，失败返回 None。"""
        async with self._semaphore:
            try:
                resp = await self._do_fetch(url)
                return self._parse_response(resp, url)
            except Exception as exc:
                logger.error(
                    "Scrapling[%s] 抓取失败 [%s]: %s",
                    self._fetcher_type, url, exc,
                )
                return None

    async def _do_fetch(self, url: str):
        """根据 fetcher_type 分发到对应的 Scrapling 引擎。"""
        if self._fetcher_type == "async":
            from scrapling import AsyncFetcher
            fetcher = AsyncFetcher()
            return await fetcher.get(url, timeout=self._timeout)

        elif self._fetcher_type == "stealthy":
            from scrapling import StealthyFetcher
            sf = StealthyFetcher()
            return await sf.async_fetch(
                url,
                headless=self._headless,
                network_idle=True,
                timeout=self._timeout * 1000,  # 转为毫秒
            )

        elif self._fetcher_type == "dynamic":
            from scrapling import DynamicFetcher
            df = DynamicFetcher()
            # DynamicFetcher.fetch 是同步方法，需 run_in_executor 避免阻塞事件循环
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                None,
                lambda: df.fetch(
                    url,
                    headless=self._headless,
                    network_idle=True,
                    timeout=self._timeout * 1000,
                ),
            )

        else:
            raise ValueError(f"未知的 Scrapling 引擎类型：{self._fetcher_type}")

    def _parse_response(self, resp, url: str) -> Optional[ArticleInsight]:
        """从 Scrapling Response 中提取元数据并转换为 Markdown。"""
        # 获取 HTML 内容
        html = str(resp.html_content) if hasattr(resp, "html_content") else ""
        if not html:
            # 回退到 body
            html = resp.body.decode("utf-8", errors="replace") if resp.body else ""

        if not html:
            logger.warning("Scrapling 返回空内容 [%s]", url)
            return None

        # HTML → Markdown，过滤噪声标签
        md_text = md(
            html,
            strip=["nav", "footer", "header", "aside", "script", "style"],
        )

        if len(md_text.strip()) < _MIN_CONTENT_LENGTH:
            logger.warning(
                "正文过短，跳过 [%s]（%d 字符，阈值 %d）",
                url, len(md_text.strip()), _MIN_CONTENT_LENGTH,
            )
            return None

        # 提取 meta 标签
        title = self._meta(resp, "og:title") or self._title_tag(resp) or url
        author = self._meta(resp, "author") or self._meta(resp, "article:author")
        publish_date = (
            self._meta(resp, "article:published_time")
            or self._meta(resp, "datePublished")
            or self._meta(resp, "date")
        )
        cover_image_url = (
            self._meta(resp, "og:image") or self._meta(resp, "twitter:image")
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

    @staticmethod
    def _meta(resp, name: str) -> Optional[str]:
        """从 Scrapling Response 提取 meta 标签内容。"""
        # 先尝试 property 属性（og: 系列）
        els = resp.css(f'meta[property="{name}"]')
        if els:
            val = els[0].attrib.get("content")
            if val:
                return str(val).strip()
        # 再尝试 name 属性
        els = resp.css(f'meta[name="{name}"]')
        if els:
            val = els[0].attrib.get("content")
            if val:
                return str(val).strip()
        return None

    @staticmethod
    def _title_tag(resp) -> Optional[str]:
        """提取 <title> 标签内容。"""
        titles = resp.css("title")
        if titles:
            text = str(titles[0].text).strip()
            return text if text else None
        return None
