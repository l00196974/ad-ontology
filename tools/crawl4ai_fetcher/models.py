"""
models.py — 数据模型层

定义 ArticleInsight 数据契约（Pydantic v2）。
本模块不依赖任何本地模块，是 fetcher 和 storage 的共同基础。
替换抓取引擎或存储后端时，此文件无需改动。
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator


class ArticleInsight(BaseModel):
    """广告资讯文章数据模型。

    Attributes:
        url:              文章 URL，作为唯一主键。
        title:            文章标题。
        author:           作者（可选，部分站点不提供）。
        publish_date:     发布日期字符串（可选，保留原始格式避免解析失败）。
        cover_image_url:  封面图 URL，来源于 og:image meta 标签（可选）。
        content_markdown: 清洗后的纯净 Markdown 正文。
        content_hash:     正文 SHA-256 哈希，用于去重（可选，由编排层计算）。
        crawl_time:       抓取时间（UTC datetime，由 fetcher 在抓取时写入）。
    """

    url: str
    title: str
    author: Optional[str] = None
    publish_date: Optional[str] = None
    cover_image_url: Optional[str] = None
    content_markdown: str
    content_hash: Optional[str] = None
    crawl_time: datetime

    @field_validator("url")
    @classmethod
    def url_must_be_nonempty(cls, v: str) -> str:
        """确保 URL 非空，去除首尾空白。"""
        v = v.strip()
        if not v:
            raise ValueError("url 不能为空字符串")
        return v

    @field_validator("content_markdown")
    @classmethod
    def content_must_be_nonempty(cls, v: str) -> str:
        """Markdown 正文不能为空（fetcher 层已做长度前置检查，此处为双重保障）。"""
        if not v or not v.strip():
            raise ValueError("content_markdown 不能为空")
        return v
