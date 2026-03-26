"""
wechat_fetcher.py — 微信公众号抓取引擎

通过微信公众号管理后台 API 获取文章列表，直接请求文章页 HTML 并转为 Markdown。

认证参数通过环境变量提供：
  - WECHAT_COOKIE: 公众号后台 cookie
  - WECHAT_TOKEN:  公众号后台 token

获取方式：登录 https://mp.weixin.qq.com/ → 浏览器开发者工具 → Network → 找任意请求的 cookie 和 token 参数。

参考项目：https://github.com/wnma3mz/wechat_articles_spider
"""

import asyncio
import logging
import re
import time
from datetime import datetime, timezone
from typing import Optional

import requests
from markdownify import markdownify as md

from base_fetcher import BaseFetcher
from models import ArticleInsight

logger = logging.getLogger(__name__)

# 最短有效正文字符数
_MIN_CONTENT_LENGTH = 100

# 微信公众号后台 API
_SEARCH_BIZ_URL = "https://mp.weixin.qq.com/cgi-bin/searchbiz"
_APPMSG_URL = "https://mp.weixin.qq.com/cgi-bin/appmsg"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
}


class WechatFetcher(BaseFetcher):
    """微信公众号文章抓取引擎。

    两阶段流程：
      Phase 1: 调用公众号后台 API 获取文章列表（需认证）
      Phase 2: 文章页是公开 URL，直接用 requests 抓取 HTML → markdownify 转 Markdown

    Args:
        cookie:  公众号后台 cookie（WECHAT_COOKIE 环境变量）
        token:   公众号后台 token（WECHAT_TOKEN 环境变量）
        delay:   请求间隔秒数，避免触发频率限制，默认 3 秒
    """

    def __init__(
        self,
        cookie: str,
        token: str,
        delay: float = 3.0,
    ) -> None:
        self._session = requests.Session()
        self._session.headers.update(_HEADERS)
        self._session.headers["Cookie"] = cookie
        self._token = token
        self._delay = delay

    # ------------------------------------------------------------------ #
    # Phase 1: 文章列表发现                                                 #
    # ------------------------------------------------------------------ #

    def _search_biz(self, nickname: str) -> Optional[str]:
        """根据公众号名称搜索获取 fakeid。"""
        params = {
            "action": "search_biz",
            "begin": "0",
            "count": "5",
            "query": nickname,
            "token": self._token,
            "lang": "zh_CN",
            "f": "json",
            "ajax": "1",
        }
        try:
            resp = self._session.get(_SEARCH_BIZ_URL, params=params, timeout=15)
            data = resp.json()
            biz_list = data.get("list", [])
            if not biz_list:
                logger.warning("未找到公众号 [%s]", nickname)
                return None
            fakeid = biz_list[0].get("fakeid")
            logger.info(
                "公众号搜索 [%s] → fakeid=%s, nickname=%s",
                nickname, fakeid, biz_list[0].get("nickname"),
            )
            return fakeid
        except Exception as exc:
            logger.error("搜索公众号失败 [%s]: %s", nickname, exc)
            return None

    def _get_article_list(
        self, fakeid: str, count: int = 5, begin: int = 0,
    ) -> list[dict]:
        """通过公众号后台 API 获取文章列表。

        Returns:
            [{title, link, cover, digest, update_time}, ...]
        """
        params = {
            "action": "list_ex",
            "begin": str(begin),
            "count": str(count),
            "fakeid": fakeid,
            "type": "9",
            "query": "",
            "token": self._token,
            "lang": "zh_CN",
            "f": "json",
            "ajax": "1",
        }
        try:
            resp = self._session.get(_APPMSG_URL, params=params, timeout=15)
            data = resp.json()

            base_resp = data.get("base_resp", {})
            if base_resp.get("ret") != 0:
                logger.error(
                    "获取文章列表失败：ret=%s, err_msg=%s",
                    base_resp.get("ret"), base_resp.get("err_msg"),
                )
                return []

            articles = data.get("app_msg_list", [])
            logger.info("获取到 %d 篇文章（begin=%d）", len(articles), begin)
            return articles

        except Exception as exc:
            logger.error("获取文章列表异常: %s", exc)
            return []

    async def fetch_article_urls(
        self,
        accounts: list[str],
        count: int = 5,
        max_pages: int = 1,
    ) -> list[dict]:
        """Phase 1: 从公众号列表获取文章信息。

        Args:
            accounts: 公众号 nickname 或 fakeid 列表
            count:    每页文章数（1-5）
            max_pages: 最多翻几页

        Returns:
            [{title, link, cover, digest, update_time}, ...]
        """
        all_articles = []

        for account in accounts:
            # 判断是 nickname 还是 fakeid（fakeid 通常是纯数字）
            if account.isdigit() or (len(account) > 10 and account.isalnum()):
                fakeid = account
            else:
                fakeid = self._search_biz(account)
                if not fakeid:
                    continue
                # 搜索后等待，避免频率限制
                await asyncio.sleep(self._delay)

            for page in range(max_pages):
                begin = page * count
                articles = self._get_article_list(fakeid, count=count, begin=begin)
                if not articles:
                    break
                all_articles.extend(articles)
                if page < max_pages - 1:
                    logger.info("等待 %.1f 秒后翻页...", self._delay)
                    await asyncio.sleep(self._delay)

        logger.info("Phase 1 完成：共获取 %d 篇文章 URL", len(all_articles))
        return all_articles

    # ------------------------------------------------------------------ #
    # Phase 2: 文章内容抓取                                                 #
    # ------------------------------------------------------------------ #

    async def fetch_all(self, urls: list[str]) -> list[ArticleInsight]:
        """抓取微信文章 URL 列表，返回 ArticleInsight 列表。"""
        results = []
        for i, url in enumerate(urls):
            article = await self.fetch_one(url)
            if article:
                results.append(article)
            # 请求间隔
            if i < len(urls) - 1:
                await asyncio.sleep(self._delay)

        logger.info("Wechat 抓取完成：%d/%d 条成功", len(results), len(urls))
        return results

    async def fetch_one(self, url: str) -> Optional[ArticleInsight]:
        """抓取单篇微信文章。"""
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=30)
            resp.encoding = "utf-8"
            html = resp.text

            if len(html) < _MIN_CONTENT_LENGTH:
                logger.warning("微信文章内容过短 [%s]（%d 字符）", url, len(html))
                return None

            # 检测频率限制
            if "你的访问过于频繁" in html or "访问过于频繁" in html:
                logger.error("微信频率限制，跳过 [%s]", url)
                return None

            return self._parse_article(html, url)

        except Exception as exc:
            logger.error("微信文章抓取失败 [%s]: %s", url, exc)
            return None

    def _parse_article(self, html: str, url: str) -> Optional[ArticleInsight]:
        """从微信文章 HTML 中提取元数据和正文 Markdown。"""
        # 标题
        title = self._extract_title(html) or url

        # 作者 / 公众号名称
        author = self._extract_author(html)

        # 发布时间
        publish_date = self._extract_publish_time(html)

        # 封面图
        cover_image_url = self._extract_meta(html, "og:image")

        # 正文 → Markdown
        # 微信文章正文在 <div class="rich_media_content" ...>...</div> 中
        content_html = self._extract_content_html(html)
        if not content_html:
            logger.warning("未找到文章正文 [%s]", url)
            return None

        # data-src → src（微信图片延迟加载）
        content_html = content_html.replace("data-src=", "src=")

        md_text = md(
            content_html,
            strip=["script", "style"],
        )

        if len(md_text.strip()) < _MIN_CONTENT_LENGTH:
            logger.warning(
                "正文过短，跳过 [%s]（%d 字符，阈值 %d）",
                url, len(md_text.strip()), _MIN_CONTENT_LENGTH,
            )
            return None

        return ArticleInsight(
            url=url,
            title=title,
            author=author,
            publish_date=publish_date,
            cover_image_url=cover_image_url,
            content_markdown=md_text,
            crawl_time=datetime.now(tz=timezone.utc),
        )

    # ------------------------------------------------------------------ #
    # HTML 解析辅助方法                                                     #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _extract_title(html: str) -> Optional[str]:
        """提取文章标题。"""
        # 优先从 og:title
        match = re.search(r'property="og:title"\s+content="([^"]+)"', html)
        if match:
            return match.group(1).strip()
        # 从 <h1> 或 <h2> 标签
        for tag in ("h2", "h1"):
            match = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", html, re.DOTALL)
            if match:
                text = re.sub(r"<[^>]+>", "", match.group(1)).strip()
                if text:
                    return text
        return None

    @staticmethod
    def _extract_author(html: str) -> Optional[str]:
        """提取作者或公众号名称。"""
        # profile_nickname
        match = re.search(r'class="profile_nickname"[^>]*>(.*?)</strong', html, re.DOTALL)
        if match:
            text = re.sub(r"<[^>]+>", "", match.group(1)).strip()
            if text:
                return text
        # js_name
        match = re.search(r'id="js_name"[^>]*>(.*?)</a', html, re.DOTALL)
        if match:
            text = re.sub(r"<[^>]+>", "", match.group(1)).strip()
            if text:
                return text
        return None

    @staticmethod
    def _extract_publish_time(html: str) -> Optional[str]:
        """提取发布时间戳并转为 ISO 格式。"""
        # var ct = "1234567890";
        match = re.search(r'ct\s*=\s*"(\d+)"', html)
        if not match:
            match = re.search(r"ct\s*=\s*(\d+)", html)
        if match:
            try:
                ts = int(match.group(1))
                return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
            except (ValueError, OSError):
                pass
        return None

    @staticmethod
    def _extract_content_html(html: str) -> Optional[str]:
        """提取文章正文 HTML。"""
        # <div class="rich_media_content" ...>...</div>
        match = re.search(
            r'<div[^>]*class="rich_media_content[^"]*"[^>]*>(.*?)</div>\s*'
            r'(?:<div[^>]*class="(?:ct_mpda_wrp|rich_media_tool)',
            html,
            re.DOTALL,
        )
        if match:
            return match.group(1)

        # 回退：更宽松的匹配
        match = re.search(
            r'<div[^>]*class="rich_media_content[^"]*"[^>]*>(.*)',
            html,
            re.DOTALL,
        )
        if match:
            # 截取到 rich_media_area_extra 或 rich_media_tool
            content = match.group(1)
            end_markers = [
                "rich_media_tool",
                "rich_media_area_extra",
                "ct_mpda_wrp",
                "id=\"js_pc_qr_code\"",
            ]
            for marker in end_markers:
                idx = content.find(marker)
                if idx > 0:
                    # 往回找最近的 <div
                    last_div = content.rfind("<div", 0, idx)
                    if last_div > 0:
                        content = content[:last_div]
                    break
            return content

        return None

    @staticmethod
    def _extract_meta(html: str, prop: str) -> Optional[str]:
        """提取 meta 标签内容。"""
        match = re.search(
            rf'property="{prop}"\s+content="([^"]+)"', html,
        )
        if match:
            return match.group(1).strip()
        return None
