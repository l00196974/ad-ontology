"""
base_fetcher.py — 抽象基类

定义所有抓取引擎的统一接口，确保 crawl4ai 和 Scrapling
（以及未来其他引擎）对外暴露一致的 API。

新增引擎时，只需继承 BaseFetcher 并实现 fetch_all / fetch_one。
"""

from abc import ABC, abstractmethod
from typing import Optional

from models import ArticleInsight


class BaseFetcher(ABC):
    """所有抓取引擎必须实现此接口。"""

    @abstractmethod
    async def fetch_all(self, urls: list[str]) -> list[ArticleInsight]:
        """并发抓取 URL 列表，返回成功解析的文章列表。

        失败的 URL 会被跳过（记录日志），不会抛出异常。
        """
        ...

    @abstractmethod
    async def fetch_one(self, url: str) -> Optional[ArticleInsight]:
        """抓取单个 URL，失败返回 None。"""
        ...
