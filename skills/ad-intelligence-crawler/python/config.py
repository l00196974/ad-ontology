"""
config.py — YAML 配置加载

支持用户通过 YAML 文件配置抓取任务，每个任务可指定不同的引擎和参数。
支持两阶段抓取：列表页发现文章链接 → 抓取文章内容。
"""

import logging
from pathlib import Path
from typing import Literal, Optional, Union

import yaml
from pydantic import BaseModel, field_validator, model_validator

logger = logging.getLogger(__name__)


class TaskOptions(BaseModel):
    """每个抓取任务的引擎配置参数。"""

    threshold: float = 0.48        # crawl4ai 剪枝阈值（0~1）
    timeout: int = 30              # 超时秒数
    concurrent: int = 3            # 最大并发数
    headless: bool = True          # 浏览器无头模式（stealthy / dynamic）


class WechatOptions(BaseModel):
    """微信公众号引擎专用配置。"""

    delay: float = 3.0             # 请求间隔秒数，避免触发频率限制
    count: int = 5                 # 每页文章数（1-5）
    max_pages: int = 1             # 最多翻几页（每页 count 篇）


class CrawlTask(BaseModel):
    """单个抓取任务组。

    支持多种模式：
      - 直接模式：通过 urls 指定文章 URL
      - 列表页模式：通过 listing_urls 指定列表页，自动发现文章链接
      - 混合模式：同时使用 urls 和 listing_urls
      - 微信模式：通过 wechat_accounts 指定公众号，自动获取文章列表
    """

    name: str
    engine: Literal["crawl4ai", "scrapling", "wechat"] = "crawl4ai"
    fetcher_type: Literal["async", "stealthy", "dynamic"] = "async"

    # 直接文章 URL（可选，默认空）
    urls: list[str] = []

    # --- 列表页两阶段抓取 ---
    listing_urls: list[str] = []                                    # 列表页 URL
    max_articles: int = 20                                          # 每个列表页最多提取文章数
    link_pattern: Optional[str] = None                              # 可选正则过滤
    link_selector: Optional[str] = None                             # 可选 CSS 选择器（scrapling）

    # --- 微信公众号模式 ---
    wechat_accounts: list[str] = []                                     # 公众号 nickname 或 fakeid 列表
    wechat_options: Optional[WechatOptions] = None                      # 微信引擎专用配置

    # --- 文章页引擎覆盖（可与列表页不同）---
    article_engine: Optional[Literal["crawl4ai", "scrapling", "wechat"]] = None
    article_fetcher_type: Literal["async", "stealthy", "dynamic"] = "async"
    article_options: Optional[TaskOptions] = None

    options: TaskOptions = TaskOptions()

    @field_validator("urls", mode="before")
    @classmethod
    def clean_urls(cls, v):
        if v is None:
            return []
        return [u.strip() for u in v if isinstance(u, str) and u.strip()]

    @field_validator("listing_urls", mode="before")
    @classmethod
    def clean_listing_urls(cls, v):
        if v is None:
            return []
        return [u.strip() for u in v if isinstance(u, str) and u.strip()]

    @field_validator("wechat_accounts", mode="before")
    @classmethod
    def clean_wechat_accounts(cls, v):
        if v is None:
            return []
        return [a.strip() for a in v if isinstance(a, str) and a.strip()]

    @model_validator(mode="after")
    def check_urls_or_listing(self):
        """根据引擎类型验证必要字段。"""
        if self.engine == "wechat":
            if not self.wechat_accounts:
                raise ValueError("wechat 引擎必须指定 wechat_accounts")
        else:
            if not self.urls and not self.listing_urls:
                raise ValueError("urls 和 listing_urls 不能同时为空，至少提供一个")
        return self


class CrawlConfig(BaseModel):
    """顶层 YAML 配置。"""

    tasks: list[CrawlTask]
    db_path: str = "articles.db"

    @field_validator("tasks")
    @classmethod
    def tasks_must_be_nonempty(cls, v: list[CrawlTask]) -> list[CrawlTask]:
        if not v:
            raise ValueError("tasks 列表不能为空")
        return v


def load_config(path: Union[str, Path]) -> CrawlConfig:
    """加载并验证 YAML 配置文件。"""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在：{path}")

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    config = CrawlConfig.model_validate(raw)
    total_direct = sum(len(t.urls) for t in config.tasks)
    total_listing = sum(len(t.listing_urls) for t in config.tasks)
    logger.info(
        "已加载配置：%d 个任务组，%d 个直接 URL，%d 个列表页，数据库=%s",
        len(config.tasks), total_direct, total_listing, config.db_path,
    )
    return config
